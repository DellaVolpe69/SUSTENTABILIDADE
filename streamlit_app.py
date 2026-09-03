import streamlit as st
import pandas as pd
import supabase
import sys
import subprocess
from pathlib import Path, PureWindowsPath
from datetime import datetime, timedelta, date
import os
import tempfile
import base64
import io
from PIL import Image, ImageOps
from requests_oauthlib import OAuth2Session
import requests

# Configuração da página — DEVE ser a primeira chamada Streamlit
st.set_page_config(page_title="Template-Sustentabilidade", layout="wide")

# Configuração Supabase
modulos_dir = Path(__file__).parent / "Modulos"

# Se o diretório ainda não existir, faz o clone direto do GitHub
if not modulos_dir.exists():
    print("📥 Clonando repositório Modulos do GitHub...")
    subprocess.run(
        [
            "git",
            "clone",
            "https://github.com/DellaVolpe69/Modulos.git",
            str(modulos_dir),
        ],
        check=True,
    )

# Garante que o diretório está no caminho de importação
if str(modulos_dir) not in sys.path:
    sys.path.insert(0, str(modulos_dir))

# ------------------------------------------------
# CREDENCIAIS DO SUPABASE (ponte secrets -> ambiente)
# ------------------------------------------------
# ConectionSupaBase.py lê SUPABASE_URL / SUPABASE_KEY de os.getenv() no
# nível do módulo, ou seja, NO MOMENTO DO IMPORT — e st.secrets não popula
# o ambiente. Sem esta ponte, e sem ela vir antes do import, conexao()
# levanta ValueError mesmo com os secrets preenchidos no Streamlit Cloud.


def secret(*nomes):
    """Primeiro secret existente entre os nomes aceitos."""
    for nome in nomes:
        try:
            if nome in st.secrets:
                return st.secrets[nome]
        except Exception:
            pass
    return None


def credenciais_supabase():
    """(url, key) lidos na hora da chamada — secrets primeiro, ambiente depois.

    Quem precisa da informação chama esta função em vez de depender de uma
    global definida 400 linhas acima.
    """
    url = secret("SUPABASE_URL", "supabase_url") or os.getenv("SUPABASE_URL")
    key = (
        secret(
            "SUPABASE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "supabase_key",
        )
        or os.getenv("SUPABASE_KEY")
    )
    return url, key


# Publica no ambiente ANTES do import de Modulos — é a única janela em que
# ConectionSupaBase consegue ler.
SUPABASE_URL, SUPABASE_KEY = credenciais_supabase()
if SUPABASE_URL:
    os.environ["SUPABASE_URL"] = str(SUPABASE_URL)
if SUPABASE_KEY:
    os.environ["SUPABASE_KEY"] = str(SUPABASE_KEY)


import Modulos.Minio.examples.MinIO as meu_minio
from Modulos import ConectionSupaBase

# ================================================
# AUTENTICAÇÃO AZURE AD (INLINE)
# ================================================
# O código de login foi trazido para dentro do app (em vez de importar
# o módulo AzureLogin). Isso garante que o fluxo OAuth seja reexecutado
# do zero a cada sessão, dependendo SOMENTE de st.session_state — que é
# isolado por usuário. Importar o módulo fazia o estado de login ficar
# no namespace do módulo (compartilhado entre todas as sessões do
# processo), o que causava o vazamento de sessão entre usuários.

url_imagem = "https://raw.githubusercontent.com/DellaVolpe69/Images/main/AppBackground02.png"
url_logo = "https://raw.githubusercontent.com/DellaVolpe69/Images/main/DellaVolpeLogoBranco.png"



# ================================================
# CONTROLE DE ACESSO
# ================================================
# Conjunto de usuários que podem acessar o app.

USUARIOS_AUTORIZADOS = {
    "elaine.queiroz@dellavolpe.com.br",
    "alicia.bitencourt@dellavolpe.com.br",
    "juliana.mendes@dellavolpe.com.br",
    "anderson.junior@dellavolpe.com.br",  # acesso para testes
}

# CSS de fundo
st.markdown(
    f"""
    <style>
    .stApp {{
        background: linear-gradient(rgba(0,0,0,0.7), rgba(0,0,0,0.7)),
            url("{url_imagem}");
        background-size: cover;
    }}
    header, [data-testid="stHeader"] {{
        background: transparent;
    }}
    .stExpander, .st-emotion-cache-16idsys, .stCard {{
        background: rgba(0,0,0,0.35) !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Configurações do Azure AD OAuth2
client_id = st.secrets["AZURE_CLIENT_ID"]
client_secret = st.secrets["AZURE_CLIENT_SECRET"]
redirect_uri = st.secrets["AZURE_REDIRECT_URI"]
authorization_base_url = st.secrets["AZURE_AUTH_URL"]
token_url = st.secrets["AZURE_TOKEN_URL"]
scope = [
    "openid",
    "email",
    "profile",
    "https://graph.microsoft.com/User.Read",
]

# Autenticação OAuth
if "token" not in st.session_state:
    st.session_state["token"] = None

query_params = st.query_params
if "code" in query_params and st.session_state["token"] is None:
    code = query_params["code"]
    azure = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
    try:
        token = azure.fetch_token(
            token_url,
            client_secret=client_secret,
            code=code,
        )
        st.session_state["token"] = token
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        if "Scope has changed" in str(e):
            st.warning("Escopos alterados. É necessário iniciar um novo login.")
            st.session_state["token"] = None
            st.query_params.clear()
            azure = OAuth2Session(client_id, scope=scope, redirect_uri=redirect_uri)
            authorization_url, state = azure.authorization_url(
                authorization_base_url, prompt="select_account"
            )
            st.link_button("🔐 Iniciar novo login", authorization_url)
            st.stop()
        else:
            st.error(f"Erro ao obter token: {e}")
            st.stop()

if st.session_state["token"] is None:
    azure = OAuth2Session(client_id, scope=scope, redirect_uri=redirect_uri)
    authorization_url, state = azure.authorization_url(
        authorization_base_url, prompt="select_account"
    )

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.image(url_logo, caption=None, use_container_width=False)

    esp1, centro, esp2 = st.columns([1, 1, 1])
    with centro:
        st.markdown(
            """
            <style>
            .custom-login-btn {
                background-color: #FF5D01 !important;
                color: white !important;
                border: 2px solid white !important;
                padding: 0.6em 1.2em;
                border-radius: 10px !important;
                font-size: 1rem;
                font-weight: 500;
                cursor: pointer;
                transition: 0.2s ease;
                text-decoration: none !important;
                display: inline-block;
            }
            .custom-login-btn:hover {
                background-color: white !important;
                color: #FF5D01 !important;
                transform: scale(1.03);
                border: 2px solid #FF5D01 !important;
            }
            .center-container {
                text-align: center;
                margin-top: 10px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="center-container">
                <a href="{authorization_url}" class="custom-login-btn">
                    🔐 Login com Microsoft
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()

# Usuário autenticado — busca o perfil
azure = OAuth2Session(client_id, token=st.session_state["token"])
me_resp = azure.get("https://graph.microsoft.com/v1.0/me")
if me_resp.status_code != 200:
    st.error(f"Falha ao obter perfil do usuário ({me_resp.status_code}): {me_resp.text}")
    st.stop()

user_info = me_resp.json()
user_name = user_info.get("displayName", "Usuário")
user_email = (
    user_info.get("mail")
    or user_info.get("userPrincipalName")
    or "desconhecido"
)

# Validação de acesso — apenas e-mails explicitamente autorizados
if not isinstance(user_email, str) or user_email.strip().lower() not in USUARIOS_AUTORIZADOS:
    st.error("Acesso não autorizado. Entre em contato com o administrador do painel.")
    st.stop()

# Salva no session_state
st.session_state["user_name"] = user_name
st.session_state["user_email"] = user_email

# ================================================
# CONEXÃO SUPABASE
# ================================================
# O cliente é criado sob demanda em conectar_supabase(), com cache_resource.

# Só chega aqui quem já está autenticado e validado acima.
usuario_email_logado = user_email.lower()

# ================================================
# TABELAS E COLUNAS DO SUPABASE
# ================================================
TABELAS_DB = {
    "consumos": "SUSTENTABILIDADE_CONSUMO",
    "licencas": "SUSTENTABILIDADE_LICENCAS",
    "custos": "SUSTENTABILIDADE_CUSTO",
    "reciclaveis": "SUSTENTABILIDADE_RECICLAVEIS",
}

# Nomes que apareciam cortados na tela do Supabase. Se algum divergir, o
# insert falha citando a coluna — corrija aqui, num lugar só.
COL_SOLIDOS = "SOLIDOS_CONTAMINADOS"
COL_OLEO = "OLEO_LUBRIFICANTE"
COL_DT_VENCIMENTO = "DT_VENCIMENTO"
COL_DIAS = "DIAS"  # dias pré-vencimento
COL_DATA_PAGAMENTO = "DATA_PAGAMENTO"


@st.cache_resource(show_spinner=False)
def conectar_supabase():
    """Um cliente por processo — create_client a cada rerun é desperdício."""
    return ConectionSupaBase.conexao()


def json_seguro(dados: dict) -> dict:
    """date/datetime não são serializáveis em JSON; o cliente quebraria."""
    saida = {}
    for chave, valor in dados.items():
        if isinstance(valor, (datetime, date)):
            saida[chave] = valor.isoformat()
        elif hasattr(valor, "item"):  # escalares numpy vindos dos inputs
            saida[chave] = valor.item()
        else:
            saida[chave] = valor
    return saida


def inserir(tabela_app: str, dados: dict):
    """Grava no Supabase. Devolve (ok, mensagem, linha_criada).

    A linha é necessária para nomear o objeto no MinIO com o id do registro.
    """
    try:
        cliente = conectar_supabase()
        resposta = (
            cliente.table(TABELAS_DB[tabela_app]).insert(json_seguro(dados)).execute()
        )
        linha = (resposta.data or [{}])[0]
        return True, "Registro gravado no Supabase.", linha
    except Exception as erro:
        return False, f"Não gravou: {erro}", {}


def remover(tabela_app: str, id_registro) -> bool:
    """Desfaz um insert. Exige política de DELETE na RLS."""
    try:
        cliente = conectar_supabase()
        cliente.table(TABELAS_DB[tabela_app]).delete().eq("id", id_registro).execute()
        return True
    except Exception:
        return False


def listar_registros(tabela_app: str, limite: int = 50) -> pd.DataFrame:
    cliente = conectar_supabase()
    resposta = (
        cliente.table(TABELAS_DB[tabela_app])
        .select("*")
        .order("id", desc=True)
        .limit(limite)
        .execute()
    )
    return pd.DataFrame(resposta.data or [])


def concluir(
    chave_msg: str,
    tabela_app: str,
    dados: dict,
    campos: tuple,
    apos_ok=None,
    apos_insert=None,
) -> None:
    """Grava e só limpa os campos se tudo passou — falha não apaga o que foi
    digitado.

    apos_insert recebe a linha criada e roda ainda dentro do "salvamento": se
    levantar exceção (ex.: upload da evidência falhou), o insert é desfeito,
    para não sobrar registro sem anexo.
    """
    ok, msg, linha = inserir(tabela_app, dados)

    if ok and apos_insert is not None:
        try:
            msg = apos_insert(linha) or msg
        except Exception as erro:
            ok = False
            id_registro = linha.get("id")
            if remover(tabela_app, id_registro):
                msg = f"Nada foi salvo — falha na evidência: {erro}"
            else:
                msg = (
                    f"ATENÇÃO: o registro id={id_registro} ficou gravado SEM "
                    f"evidência e não foi possível desfazer (falta política de "
                    f"DELETE na RLS?). Exclua na mão. Falha original: {erro}"
                )

    st.session_state[chave_msg] = ("success" if ok else "error", msg)
    if not ok:
        return
    for campo in campos:
        st.session_state.pop(campo, None)
    if apos_ok is not None:
        apos_ok()


def render_msg(chave_msg: str) -> None:
    tipo, texto = st.session_state.pop(chave_msg, (None, None))
    if tipo == "success":
        st.success(texto)
    elif tipo == "warning":
        st.warning(texto)
    elif tipo == "error":
        st.error(texto)


def fmt_brl(valor: float) -> str:
    """Formata no padrão pt-BR: 1234.5 -> R$ 1.234,50"""
    texto = f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {texto}"


def txt(chave: str) -> str:
    return str(st.session_state.get(chave, "")).strip()


# ================================================
# MINIO — EVIDÊNCIAS
# ================================================
# Bucket seguindo o padrão dos que já existem (minúsculo com hífen).
# create_bucket_if_not_exists() cria no primeiro upload.
BUCKET_LICENCAS = "sustentabilidade-licencas"


def subir_evidencia(id_registro, arquivo, sequencia: int = 1) -> str:
    """Sobe o anexo e devolve o nome do objeto.

    Nome no padrão <id>_<n>.<ext>, que é o que Modulos.Minio listar_anexos()
    procura (prefixo "<id>_") — assim o vínculo licença↔arquivo não precisa de
    coluna no Supabase.

    Usa put_object com os bytes em memória em vez de meu_minio.upload(), que
    exige arquivo em disco (fput_object) — no Streamlit Cloud o disco é
    efêmero e o UploadedFile já está na memória.
    """
    manager = getattr(meu_minio, "manager", None)
    if manager is None:
        raise RuntimeError(
            "MinIO indisponível — o módulo abre a conexão no import e ela "
            "falhou. Confira MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/SECURE nos "
            "secrets e reinicie o app (o manager não se reconecta sozinho)."
        )

    extensao = Path(arquivo.name).suffix.lower() or ".bin"
    objeto = f"{id_registro}_{sequencia}{extensao}"
    conteudo = arquivo.getvalue()

    manager.create_bucket_if_not_exists(BUCKET_LICENCAS)
    manager.client.put_object(
        BUCKET_LICENCAS,
        objeto,
        io.BytesIO(conteudo),
        length=len(conteudo),
        content_type=arquivo.type or "application/octet-stream",
    )
    return objeto


def excluir_evidencias(id_registro) -> int:
    """Remove do bucket os anexos <id>_* e devolve quantos saíram.

    Sem isso, excluir a licença deixa o arquivo órfão no MinIO: ninguém mais
    chega nele, porque o vínculo era justamente o id.
    """
    manager = getattr(meu_minio, "manager", None)
    if manager is None:
        raise RuntimeError("MinIO indisponível — nenhum anexo foi apagado")

    removidos = 0
    for obj in manager.client.list_objects(
        BUCKET_LICENCAS, prefix=f"{id_registro}_", recursive=True
    ):
        manager.client.remove_object(BUCKET_LICENCAS, obj.object_name)
        removidos += 1
    return removidos




# ================================================
# CRUD — GRADE EDITÁVEL
# ================================================
# Uma implementação serve as 4 telas: st.data_editor devolve o que mudou em
# st.session_state[chave] como {"edited_rows", "deleted_rows", "added_rows"},
# e aqui isso é traduzido em update/delete no Supabase.
#
# Inclusão NÃO passa pela grade: cada tela tem regra própria (FILIAL
# obrigatória, evidência obrigatória na licença) e uma linha digitada direto
# no grid fura essas validações. Linhas adicionadas na grade são recusadas
# com aviso, e o formulário acima segue sendo o único caminho de criação.

BLOQUEADAS_PADRAO = ("id", "DATA_CRIACAO", "USUARIO")


def atualizar(tabela_app: str, id_registro, mudancas: dict) -> None:
    cliente = conectar_supabase()
    cliente.table(TABELAS_DB[tabela_app]).update(json_seguro(mudancas)).eq(
        "id", id_registro
    ).execute()


def excluir(tabela_app: str, id_registro) -> None:
    cliente = conectar_supabase()
    cliente.table(TABELAS_DB[tabela_app]).delete().eq("id", id_registro).execute()


def estado_editor(chave: str) -> dict:
    """Normaliza o estado do data_editor para um dict simples."""
    bruto = st.session_state.get(chave)
    if bruto is None:
        return {}
    if isinstance(bruto, dict):
        return bruto
    return {
        "edited_rows": getattr(bruto, "edited_rows", {}) or {},
        "deleted_rows": getattr(bruto, "deleted_rows", []) or [],
        "added_rows": getattr(bruto, "added_rows", []) or [],
    }


def aplicar_edicoes(
    tabela_app: str,
    chave_editor: str,
    chave_msg: str,
    chave_versao: str,
    ids: list,
    ajustar=None,
    ao_excluir=None,
) -> None:
    """Callback do botão Aplicar: manda para o banco o que foi mexido na grade.

    ids é a lista de ids na ordem em que as linhas foram exibidas — é assim
    que o índice devolvido pelo data_editor volta a ser um registro.
    """
    estado = estado_editor(chave_editor)
    editadas = estado.get("edited_rows") or {}
    excluidas = estado.get("deleted_rows") or []
    adicionadas = estado.get("added_rows") or []

    if not editadas and not excluidas and not adicionadas:
        st.session_state[chave_msg] = ("warning", "Nada foi alterado na grade.")
        return

    alterados, removidos, arquivos, erros = 0, 0, 0, []

    # --- UPDATE ---
    for indice, mudancas in editadas.items():
        try:
            id_registro = ids[int(indice)]
        except (ValueError, IndexError):
            erros.append(f"linha {indice}: fora da lista exibida")
            continue
        mudancas = {c: v for c, v in mudancas.items() if c != "id"}
        if not mudancas:
            continue
        if ajustar is not None:
            mudancas = ajustar(id_registro, mudancas)
        try:
            atualizar(tabela_app, id_registro, mudancas)
            alterados += 1
        except Exception as erro:
            erros.append(f"id {id_registro}: {erro}")

    # --- DELETE ---
    for indice in excluidas:
        try:
            id_registro = ids[int(indice)]
        except (ValueError, IndexError):
            erros.append(f"linha {indice}: fora da lista exibida")
            continue
        try:
            excluir(tabela_app, id_registro)
            removidos += 1
        except Exception as erro:
            erros.append(f"id {id_registro}: {erro}")
            continue
        # anexos só saem depois que a linha some, para não perder o arquivo
        # de um registro que continuou no banco
        if ao_excluir is not None:
            try:
                arquivos += ao_excluir(id_registro)
            except Exception as erro:
                erros.append(f"id {id_registro}: linha excluída, mas o anexo ficou ({erro})")

    partes = []
    if alterados:
        partes.append(f"{alterados} alterado(s)")
    if removidos:
        partes.append(f"{removidos} excluído(s)")
    if arquivos:
        partes.append(f"{arquivos} anexo(s) removido(s) do MinIO")
    if adicionadas:
        partes.append(
            f"{len(adicionadas)} linha(s) nova(s) IGNORADA(s) — use o formulário acima, "
            "onde as obrigatoriedades são checadas"
        )

    if erros:
        st.session_state[chave_msg] = (
            "error",
            (", ".join(partes) + " | " if partes else "") + "falhas: " + "; ".join(erros),
        )
    else:
        st.session_state[chave_msg] = ("success", ", ".join(partes) + ".")

    # grade nova: descarta o diff já aplicado e recarrega do banco
    st.session_state[chave_versao] = st.session_state.get(chave_versao, 0) + 1


def tabela_editavel(
    tabela_app: str,
    colunas_config: dict = None,
    bloqueadas: tuple = (),
    colunas_data: tuple = (),
    ajustar=None,
    ao_excluir=None,
    limite: int = 200,
) -> None:
    """Read + Update + Delete da tabela, em grade."""
    st.markdown("#### Registros")

    chave_versao = f"ver_{tabela_app}"
    versao = st.session_state.setdefault(chave_versao, 0)
    chave_editor = f"editor_{tabela_app}_{versao}"
    chave_msg = f"msg_grade_{tabela_app}"

    try:
        df = listar_registros(tabela_app, limite)
    except Exception as erro:
        st.error(f"Não foi possível ler {TABELAS_DB[tabela_app]}: {erro}")
        return

    if df.empty:
        st.caption(
            "Nenhum registro. Se você acabou de gravar e nada aparece, "
            "é a RLS sem política de SELECT."
        )
        return

    if "id" not in df.columns:
        st.warning("A consulta não trouxe a coluna id — sem ela não há como editar.")
        st.dataframe(df, hide_index=True)
        return

    ids = df["id"].tolist()

    # o PostgREST devolve date como texto ("2026-09-01"); sem converter, o
    # DateColumn recebe string e não abre o calendário
    for coluna in colunas_data:
        if coluna in df.columns:
            df[coluna] = pd.to_datetime(df[coluna], errors="coerce")

    # filtra pelo que a tabela realmente tem: SUSTENTABILIDADE_CONSUMO, por
    # exemplo, não tem USUARIO
    bloqueio = [
        c for c in list(BLOQUEADAS_PADRAO) + list(bloqueadas) if c in df.columns
    ]
    config = {c: v for c, v in (colunas_config or {}).items() if c in df.columns}

    st.data_editor(
        df,
        key=chave_editor,
        num_rows="dynamic",
        hide_index=True,
        disabled=bloqueio,
        column_config=config,
    )

    esq, dir_ = st.columns([1, 3])
    with esq:
        st.button(
            "✅ Aplicar alterações",
            key=f"aplicar_{tabela_app}_{versao}",
            on_click=aplicar_edicoes,
            args=(tabela_app, chave_editor, chave_msg, chave_versao, ids),
            kwargs={"ajustar": ajustar, "ao_excluir": ao_excluir},
        )
    with dir_:
        st.caption(
            f"Editar célula ou marcar linha e usar 🗑 para excluir — nada vai ao "
            f"banco antes de Aplicar. Mostrando as {len(df)} mais recentes."
        )

    render_msg(chave_msg)

def recalcular_total_reciclavel(id_registro, mudancas: dict) -> dict:
    """TOTAL é derivado de PESO x VALOR_KG.

    A coluna não é generated no banco, então editar PESO ou VALOR_KG na grade
    deixaria o TOTAL antigo mentindo. Relê a linha para combinar o campo
    editado com o que não foi tocado.
    """
    if not ({"PESO", "VALOR_KG"} & set(mudancas)):
        return mudancas

    cliente = conectar_supabase()
    atual = (
        cliente.table(TABELAS_DB["reciclaveis"])
        .select("*")
        .eq("id", id_registro)
        .limit(1)
        .execute()
        .data
        or [{}]
    )[0]

    def valor(campo):
        bruto = mudancas.get(campo, atual.get(campo))
        return float(bruto or 0)

    mudancas = dict(mudancas)
    mudancas["TOTAL"] = round(valor("PESO") * valor("VALOR_KG"), 2)
    return mudancas


# ================================================
# NAVEGAÇÃO ENTRE TELAS
# ================================================
TELAS = {
    "consumos": "♻️ CONSUMOS E SERVIÇOS",
    "licencas": "📄 CONTROLE DE LICENÇAS",
    "custos": "💰 CUSTOS E ORÇAMENTOS",
    "reciclaveis": "🗂️ RECICLÁVEIS",
    "indicador": "📊 INDICADOR SUSTENTABILIDADE",
}

if "tela" not in st.session_state:
    st.session_state["tela"] = "menu"


def ir_para(tela: str) -> None:
    st.session_state["tela"] = tela


# CSS dos botões do menu
st.markdown(
    """
    <style>
    div[data-testid="stButton"] > button {
        background-color: rgba(0,0,0,0.35) !important;
        color: white !important;
        border: 2px solid #FF5D01 !important;
        border-radius: 12px !important;
        padding: 1.4em 1em !important;
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        width: 100% !important;
        transition: 0.2s ease;
    }
    div[data-testid="stButton"] > button:hover {
        background-color: #FF5D01 !important;
        border: 2px solid white !important;
        transform: scale(1.02);
    }
    div[data-testid="stButton"] > button:disabled {
        border-color: rgba(255,255,255,0.25) !important;
        color: rgba(255,255,255,0.45) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ================================================
# TELA INICIAL (MENU)
# ================================================
def tela_menu() -> None:
    st.image(url_logo, width=260)
    st.markdown("### Painel de Sustentabilidade")
    st.caption(f"Bem-vindo(a), {user_name} — {usuario_email_logado}")

    url_sb, key_sb = credenciais_supabase()
    if not url_sb or not key_sb:
        st.error(
            "SUPABASE_URL e/ou SUPABASE_KEY não encontrados em st.secrets — "
            "nenhuma tela vai gravar."
        )

    st.divider()

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.button(TELAS["consumos"], key="btn_consumos", on_click=ir_para, args=("consumos",))
        st.button(TELAS["custos"], key="btn_custos", on_click=ir_para, args=("custos",))
        st.button(TELAS["indicador"], key="btn_indicador", on_click=ir_para, args=("indicador",))
    with c2:
        st.button(TELAS["licencas"], key="btn_licencas", on_click=ir_para, args=("licencas",))
        st.button(TELAS["reciclaveis"], key="btn_reciclaveis", on_click=ir_para, args=("reciclaveis",))


def cabecalho_tela(chave: str) -> None:
    """Título da tela + botão de retorno ao menu."""
    esq, dir_ = st.columns([6, 1])
    with esq:
        st.markdown(f"## {TELAS[chave]}")
    with dir_:
        st.button("⬅️ Voltar", key=f"voltar_{chave}", on_click=ir_para, args=("menu",))
    st.divider()


# ================================================
# 1) CONSUMOS E SERVIÇOS  ->  SUSTENTABILIDADE_CONSUMO
# ================================================
# Nenhuma tela usa st.form: com clear_on_submit os campos seriam apagados
# também quando o insert falhasse (RLS, rede, coluna divergente), e o
# usuário perderia o que digitou. Widgets com key + callback deixam a
# limpeza condicionada ao sucesso.

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

CAMPOS_CONSUMO = (
    "con_filial",
    "con_ano",
    "con_mes",
    "con_solidos",
    "con_oleo",
    "con_agua",
    "con_energia",
    "con_comum",
    "con_madeira",
    "con_reciclaveis",
    "con_co2",
)


def competencia_consumo():
    """(ano, mes) escolhidos na tela — a tabela guarda os dois como inteiros."""
    ano = int(st.session_state.get("con_ano", date.today().year))
    nome_mes = st.session_state.get("con_mes", MESES[date.today().month - 1])
    return ano, MESES.index(nome_mes) + 1


def salvar_consumo() -> None:
    if not txt("con_filial"):
        st.session_state["msg_consumos"] = ("warning", "Informe a FILIAL.")
        return
    # SUSTENTABILIDADE_CONSUMO não tem coluna USUARIO (ver observação).
    ano, mes = competencia_consumo()
    dados = {
        "FILIAL": txt("con_filial").upper(),
        "ANO": ano,
        "MES": mes,
        COL_SOLIDOS: st.session_state.get("con_solidos", 0.0),
        COL_OLEO: st.session_state.get("con_oleo", 0.0),
        "AGUA": st.session_state.get("con_agua", 0.0),
        "ENERGIA": st.session_state.get("con_energia", 0.0),
        "COMUM": st.session_state.get("con_comum", 0.0),
        "MADEIRA": st.session_state.get("con_madeira", 0.0),
        "RECICLAVEIS": st.session_state.get("con_reciclaveis", 0.0),
        "CO2": st.session_state.get("con_co2", 0.0),
    }
    concluir("msg_consumos", "consumos", dados, CAMPOS_CONSUMO)


def tela_consumos() -> None:
    cabecalho_tela("consumos")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("FILIAL", key="con_filial")
    with c2:
        st.number_input(
            "ANO",
            min_value=2000,
            max_value=date.today().year + 1,
            value=date.today().year,
            step=1,
            format="%d",
            key="con_ano",
        )
    with c3:
        st.selectbox("MÊS", MESES, index=date.today().month - 1, key="con_mes")

    st.markdown("**Volumes / consumos**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input("SÓLIDOS CONTAMINADOS", min_value=0.0, step=0.01, format="%.2f", key="con_solidos")
        st.number_input("ENERGIA", min_value=0.0, step=0.01, format="%.2f", key="con_energia")
        st.number_input("RECICLÁVEIS", min_value=0.0, step=0.01, format="%.2f", key="con_reciclaveis")
    with c2:
        st.number_input("ÓLEO LUBRIFICANTE", min_value=0.0, step=0.01, format="%.2f", key="con_oleo")
        st.number_input("COMUM", min_value=0.0, step=0.01, format="%.2f", key="con_comum")
        st.number_input("CO²", min_value=0.0, step=0.01, format="%.2f", key="con_co2")
    with c3:
        st.number_input("ÁGUA", min_value=0.0, step=0.01, format="%.2f", key="con_agua")
        st.number_input("MADEIRA", min_value=0.0, step=0.01, format="%.2f", key="con_madeira")

    st.button("💾 Salvar", key="btn_salvar_con", on_click=salvar_consumo)
    render_msg("msg_consumos")
    tabela_editavel(
        "consumos",
        colunas_config={
            "MES": st.column_config.NumberColumn("MES", min_value=1, max_value=12, step=1),
            "ANO": st.column_config.NumberColumn("ANO", min_value=1990, max_value=2100, step=1),
        },
    )


# ================================================
# 2) CONTROLE DE LICENÇAS  ->  SUSTENTABILIDADE_LICENCAS
# ================================================
CATEGORIAS_LICENCA = ["LICENCA", "AMBIENTAL"]
OPCOES_STATUS = ["NO PRAZO", "VENCIDO", "RENOVAR", "NÃO SE APLICA"]
TIPOS_EVIDENCIA = ["png", "jpg", "jpeg", "pdf"]
CAMPOS_LICENCA = (
    "lic_filial",
    "lic_rota",
    "lic_cnpj",
    "lic_licenca",
    "lic_dt_venc",
    "lic_dias_pre",
    "lic_status",
    "lic_obs",
    "lic_categoria",
)

# O file_uploader não zera ao apagar a key; troca-se a própria key por uma
# nova (contador) para o widget nascer vazio no próximo registro.
st.session_state.setdefault("lic_upload_n", 0)


def chave_evidencia() -> str:
    return f"lic_evidencia_{st.session_state['lic_upload_n']}"


def salvar_licenca() -> None:
    arquivo = st.session_state.get(chave_evidencia())

    faltando = []
    if not txt("lic_filial"):
        faltando.append("FILIAL")
    if arquivo is None:
        faltando.append("Licença (evidência)")
    if faltando:
        st.session_state["msg_licencas"] = ("warning", "Obrigatório: " + ", ".join(faltando))
        return

    # A evidência não vai no payload: o vínculo é o nome do objeto no MinIO
    # (<id>_<n>.<ext>), que listar_anexos() encontra pelo prefixo.
    dados = {
        "FILIAL": txt("lic_filial").upper(),
        "ROTA": int(st.session_state.get("lic_rota", 0)),
        "CNPJ": txt("lic_cnpj"),
        "LICENCA": txt("lic_licenca"),
        COL_DT_VENCIMENTO: st.session_state.get("lic_dt_venc", date.today()),
        COL_DIAS: int(st.session_state.get("lic_dias_pre", 0)),
        "STATUS": st.session_state.get("lic_status", OPCOES_STATUS[0]),
        "OBSERVACAO": txt("lic_obs"),
        "CATEGORIA": st.session_state.get("lic_categoria", CATEGORIAS_LICENCA[0]),
        "USUARIO": usuario_email_logado,
    }

    def subir(linha: dict) -> str:
        id_registro = linha.get("id")
        if id_registro is None:
            raise RuntimeError(
                "o insert não devolveu o id (RLS sem política de SELECT?) e "
                "sem id não há como nomear o objeto"
            )
        objeto = subir_evidencia(id_registro, arquivo)
        return f"Licença {id_registro} salva · evidência em {BUCKET_LICENCAS}/{objeto}"

    def limpar_upload() -> None:
        st.session_state["lic_upload_n"] += 1

    concluir(
        "msg_licencas",
        "licencas",
        dados,
        CAMPOS_LICENCA,
        apos_ok=limpar_upload,
        apos_insert=subir,
    )


def tela_licencas() -> None:
    cabecalho_tela("licencas")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("FILIAL", key="lic_filial")
        st.text_input("LICENÇA", key="lic_licenca")
        st.selectbox("STATUS", OPCOES_STATUS, key="lic_status")
    with c2:
        st.number_input("ROTA", min_value=0, step=1, format="%d", key="lic_rota")
        st.date_input("DT VENCIMENTO", value=date.today(), format="DD/MM/YYYY", key="lic_dt_venc")
        st.selectbox("CATEGORIA", CATEGORIAS_LICENCA, key="lic_categoria")
    with c3:
        st.text_input("CNPJ", key="lic_cnpj")
        st.number_input("DIAS PRÉ VENCIMENTO", min_value=0, step=1, format="%d", key="lic_dias_pre")

    st.text_area("OBSERVAÇÃO", key="lic_obs")

    st.markdown("**Evidência (obrigatória)**")
    esq, dir_ = st.columns([2, 1])
    with esq:
        arquivo = st.file_uploader(
            "Licença",
            type=TIPOS_EVIDENCIA,
            key=chave_evidencia(),
            help="Imagem ou PDF da licença. Sem o anexo o registro não é salvo.",
        )
    with dir_:
        if arquivo is not None:
            if str(arquivo.type).startswith("image/"):
                st.image(arquivo, caption=arquivo.name, width=200)
            else:
                st.success(f"📎 {arquivo.name} · {arquivo.size / 1024:,.1f} KB")

    st.button("💾 Salvar", key="btn_salvar_lic", on_click=salvar_licenca, disabled=arquivo is None)
    if arquivo is None:
        st.caption("Anexe a Licença para liberar o Salvar.")

    render_msg("msg_licencas")
    tabela_editavel(
        "licencas",
        colunas_config={
            "CATEGORIA": st.column_config.SelectboxColumn(
                "CATEGORIA", options=CATEGORIAS_LICENCA
            ),
            "STATUS": st.column_config.SelectboxColumn("STATUS", options=OPCOES_STATUS),
            COL_DT_VENCIMENTO: st.column_config.DateColumn(
                COL_DT_VENCIMENTO, format="DD/MM/YYYY"
            ),
            COL_DIAS: st.column_config.NumberColumn(COL_DIAS, min_value=0, step=1),
        },
        colunas_data=(COL_DT_VENCIMENTO,),
        ao_excluir=excluir_evidencias,
    )


# ================================================
# 3) CUSTOS E ORÇAMENTOS  ->  SUSTENTABILIDADE_CUSTO
# ================================================
CAMPOS_CUSTO = (
    "cus_fornecedor",
    "cus_filial",
    "cus_nota",
    "cus_pedido",
    "cus_migo",
    "cus_ng",
    "cus_valor",
    "cus_mes",
    "cus_dt_pag",
)


def salvar_custo() -> None:
    if not txt("cus_fornecedor"):
        st.session_state["msg_custos"] = ("warning", "Informe o FORNECEDOR.")
        return
    dados = {
        "FORNECEDOR": txt("cus_fornecedor").upper(),
        "FILIAL": txt("cus_filial").upper(),
        "NOTA_BOLETO": txt("cus_nota"),
        "PEDIDO": txt("cus_pedido"),
        "MIGO": txt("cus_migo"),
        "NG": txt("cus_ng"),
        "VALOR": st.session_state.get("cus_valor", 0.0),
        "MES": int(st.session_state.get("cus_mes", date.today().month)),
        COL_DATA_PAGAMENTO: st.session_state.get("cus_dt_pag", date.today()),
        "USUARIO": usuario_email_logado,
    }
    concluir("msg_custos", "custos", dados, CAMPOS_CUSTO)


def tela_custos() -> None:
    cabecalho_tela("custos")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("FORNECEDOR", key="cus_fornecedor")
        st.text_input("PEDIDO", key="cus_pedido")
        st.number_input("VALOR", min_value=0.0, step=0.01, format="%.2f", key="cus_valor")
    with c2:
        st.text_input("FILIAL", key="cus_filial")
        st.text_input("MIGO", key="cus_migo")
        st.number_input(
            "MÊS", min_value=1, max_value=12, value=date.today().month, step=1,
            format="%d", key="cus_mes",
        )
    with c3:
        st.text_input("NOTA/BOLETO", key="cus_nota")
        st.text_input("NG", key="cus_ng")
        st.date_input("DATA PAGAMENTO", value=date.today(), format="DD/MM/YYYY", key="cus_dt_pag")

    st.button("💾 Salvar", key="btn_salvar_cus", on_click=salvar_custo)
    render_msg("msg_custos")
    tabela_editavel(
        "custos",
        colunas_config={
            "MES": st.column_config.NumberColumn("MES", min_value=1, max_value=12, step=1),
            "VALOR": st.column_config.NumberColumn("VALOR", min_value=0.0, format="%.2f"),
        },
    )


# ================================================
# 4) RECICLÁVEIS  ->  SUSTENTABILIDADE_RECICLAVEIS
# ================================================
# Sem st.form também porque o TOTAL (PESO x VALOR/KG) precisa acompanhar a
# digitação — dentro de um form só haveria rerun no submit.
CAMPOS_RECICLAVEIS = ("rec_filial", "rec_material", "rec_peso", "rec_valor_kg", "rec_pagamento")
OPCOES_PAGAMENTO = ["Pg Recebido", "Aguardando Pagamento"]


def salvar_reciclaveis() -> None:
    faltando = []
    if not txt("rec_filial"):
        faltando.append("FILIAL")
    if not txt("rec_material"):
        faltando.append("MATERIAL")
    if faltando:
        st.session_state["msg_reciclaveis"] = ("warning", "Obrigatório: " + ", ".join(faltando))
        return

    peso = float(st.session_state.get("rec_peso", 0.0))
    valor_kg = float(st.session_state.get("rec_valor_kg", 0.0))
    dados = {
        "FILIAL": txt("rec_filial").upper(),
        "DATA": st.session_state.get("rec_data", date.today()),
        "MATERIAL": txt("rec_material").upper(),
        "PESO": peso,
        "VALOR_KG": valor_kg,
        "TOTAL": round(peso * valor_kg, 2),
        "PAGAMENTO": st.session_state.get("rec_pagamento", OPCOES_PAGAMENTO[0]),
        "USUARIO": usuario_email_logado,
    }
    concluir("msg_reciclaveis", "reciclaveis", dados, CAMPOS_RECICLAVEIS)


def tela_reciclaveis() -> None:
    cabecalho_tela("reciclaveis")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("FILIAL", key="rec_filial")
        st.date_input("DATA", value=date.today(), format="DD/MM/YYYY", key="rec_data")
        peso = st.number_input("PESO", min_value=0.0, step=0.01, format="%.2f", key="rec_peso")
    with c2:
        st.text_input("MATERIAL", key="rec_material")
        valor_kg = st.number_input(
            "VALOR/KG", min_value=0.0, step=0.01, format="%.2f", key="rec_valor_kg"
        )
    with c3:
        st.selectbox("PAGAMENTO", OPCOES_PAGAMENTO, key="rec_pagamento")
        st.metric("TOTAL", fmt_brl(peso * valor_kg))

    st.button("💾 Salvar", key="btn_salvar_rec", on_click=salvar_reciclaveis)
    render_msg("msg_reciclaveis")
    tabela_editavel(
        "reciclaveis",
        colunas_config={
            "PAGAMENTO": st.column_config.SelectboxColumn(
                "PAGAMENTO", options=OPCOES_PAGAMENTO
            ),
            "DATA": st.column_config.DateColumn("DATA", format="DD/MM/YYYY"),
            "TOTAL": st.column_config.NumberColumn(
                "TOTAL", format="%.2f", help="calculado: PESO x VALOR_KG"
            ),
        },
        bloqueadas=("TOTAL",),
        colunas_data=("DATA",),
        ajustar=recalcular_total_reciclavel,
    )


# ================================================
# 5) INDICADOR SUSTENTABILIDADE
# ================================================
def tela_indicador() -> None:
    cabecalho_tela("indicador")
    st.info("Tela em construção — visualização do indicador.")


# ================================================
# ROTEADOR
# ================================================
ROTAS = {
    "menu": tela_menu,
    "consumos": tela_consumos,
    "licencas": tela_licencas,
    "custos": tela_custos,
    "reciclaveis": tela_reciclaveis,
    "indicador": tela_indicador,
}

ROTAS.get(st.session_state["tela"], tela_menu)()
