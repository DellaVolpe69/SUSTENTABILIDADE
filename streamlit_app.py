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
COL_BP = "BP FORNECEDOR"  # atenção: espaço no nome, não underscore


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


def form_consumos() -> None:
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
        "ROTA": txt("lic_rota"),  # coluna text no banco
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


def form_licencas() -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("FILIAL", key="lic_filial")
        st.text_input("LICENÇA", key="lic_licenca")
        st.selectbox("STATUS", OPCOES_STATUS, key="lic_status")
    with c2:
        st.text_input("ROTA", key="lic_rota")
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
    "cus_bp",
    "cus_fixo",
    "cus_setor",
)

OPCOES_SETOR = ["Sustentabilidade", "Qualidade"]


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
        COL_BP: st.session_state.get("cus_bp", 0.0),
        "FIXO": txt("cus_fixo"),
        "SETOR": st.session_state.get("cus_setor", OPCOES_SETOR[0]),
        "USUARIO": usuario_email_logado,
    }
    concluir("msg_custos", "custos", dados, CAMPOS_CUSTO)


def form_custos() -> None:
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

    c4, c5, c6 = st.columns(3)
    with c4:
        # coluna float8 no banco; step/format inteiros porque BP é identificador
        st.number_input(
            "BP FORNECEDOR", min_value=0.0, step=1.0, format="%.0f", key="cus_bp"
        )
    with c5:
        st.text_input("FIXO", key="cus_fixo")
    with c6:
        st.selectbox("SETOR", OPCOES_SETOR, key="cus_setor")

    st.button("💾 Salvar", key="btn_salvar_cus", on_click=salvar_custo)
    render_msg("msg_custos")


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


def form_reciclaveis() -> None:
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


# ================================================
# CRUD — EDIÇÃO POR REGISTRO
# ================================================
# Cada tela tem duas abas: uma para lançar (formulário com as validações) e
# uma para corrigir/excluir. Na segunda, escolhe-se o registro numa lista e
# ele abre nos mesmos campos do lançamento, com botões explícitos.
#
# A grade editável foi abandonada de propósito: editar célula e depois
# lembrar de "Aplicar" não é óbvio para quem só quer corrigir um número, e a
# exclusão ficava escondida num ícone de lixeira da tabela.

# MESES já é definido na seção da tela de consumos.


def campo(col, tipo, label=None, **extra) -> dict:
    return {"col": col, "tipo": tipo, "label": label or col, **extra}


def atualizar(tabela_app: str, id_registro, mudancas: dict) -> None:
    cliente = conectar_supabase()
    cliente.table(TABELAS_DB[tabela_app]).update(json_seguro(mudancas)).eq(
        "id", id_registro
    ).execute()


def excluir(tabela_app: str, id_registro) -> None:
    cliente = conectar_supabase()
    cliente.table(TABELAS_DB[tabela_app]).delete().eq("id", id_registro).execute()


def recalcular_total_reciclavel(registro: dict, mudancas: dict) -> dict:
    """TOTAL é derivado de PESO x VALOR_KG.

    A coluna não é generated no banco, então mudar PESO ou VALOR_KG sem
    recalcular deixaria o TOTAL antigo mentindo.
    """
    if not ({"PESO", "VALOR_KG"} & set(mudancas)):
        return mudancas

    def valor(campo_nome):
        return float(mudancas.get(campo_nome, registro.get(campo_nome)) or 0)

    mudancas = dict(mudancas)
    mudancas["TOTAL"] = round(valor("PESO") * valor("VALOR_KG"), 2)
    return mudancas


# ------------------------------------------------
# Campos de cada tabela (usados só na aba de edição)
# ------------------------------------------------
CAMPOS_EDICAO = {
    "consumos": [
        campo("FILIAL", "texto"),
        campo("ANO", "inteiro", minimo=1990, maximo=2100),
        campo("MES", "mes", "MÊS"),
        campo(COL_SOLIDOS, "decimal", "SÓLIDOS CONTAMINADOS"),
        campo(COL_OLEO, "decimal", "ÓLEO LUBRIFICANTE"),
        campo("AGUA", "decimal", "ÁGUA"),
        campo("ENERGIA", "decimal"),
        campo("COMUM", "decimal"),
        campo("MADEIRA", "decimal"),
        campo("RECICLAVEIS", "decimal", "RECICLÁVEIS"),
        campo("CO2", "decimal", "CO²"),
    ],
    "licencas": [
        campo("FILIAL", "texto"),
        campo("LICENCA", "texto", "LICENÇA"),
        campo("CNPJ", "texto"),
        campo("ROTA", "texto"),
        campo(COL_DT_VENCIMENTO, "data", "DT VENCIMENTO"),
        campo(COL_DIAS, "inteiro", "DIAS PRÉ VENCIMENTO"),
        campo("STATUS", "opcoes", opcoes=OPCOES_STATUS),
        campo("CATEGORIA", "opcoes", opcoes=CATEGORIAS_LICENCA),
        campo("OBSERVACAO", "texto_longo", "OBSERVAÇÃO"),
    ],
    "custos": [
        campo("FORNECEDOR", "texto"),
        campo("FILIAL", "texto"),
        campo("NOTA_BOLETO", "texto", "NOTA/BOLETO"),
        campo("PEDIDO", "texto"),
        campo("MIGO", "texto"),
        campo("NG", "texto"),
        campo("VALOR", "decimal"),
        campo("MES", "mes", "MÊS"),
        campo(COL_DATA_PAGAMENTO, "data", "DATA PAGAMENTO"),
        campo(COL_BP, "decimal", "BP FORNECEDOR"),
        campo("FIXO", "texto"),
        campo("SETOR", "opcoes", opcoes=OPCOES_SETOR),
    ],
    "reciclaveis": [
        campo("FILIAL", "texto"),
        campo("DATA", "data"),
        campo("MATERIAL", "texto"),
        campo("PESO", "decimal"),
        campo("VALOR_KG", "decimal", "VALOR/KG"),
        campo("TOTAL", "calculado"),
        campo("PAGAMENTO", "opcoes", opcoes=OPCOES_PAGAMENTO),
    ],
}

# colunas que compõem o rótulo do registro na lista de seleção
RESUMO_REGISTRO = {
    "consumos": ("FILIAL", "MES", "ANO"),
    "licencas": ("FILIAL", "LICENCA", "CATEGORIA"),
    "custos": ("FORNECEDOR", "NOTA_BOLETO", "VALOR"),
    "reciclaveis": ("FILIAL", "MATERIAL", "DATA"),
}

AJUSTES_EDICAO = {"reciclaveis": recalcular_total_reciclavel}


def para_int(valor, padrao=0) -> int:
    """Nunca levanta: coluna text pode guardar qualquer coisa.

    ROTA virou text no banco, então um "12A" ou "S/ROTA" chegaria aqui e
    um int() cru derrubava a tela inteira por causa de uma linha.
    """
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return padrao


def para_float(valor, padrao=0.0) -> float:
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def para_data(valor):
    """date, datetime, texto ISO ou dd/mm/aaaa. Devolve None se não der.

    DT_VENCIMENTO e DATA_PAGAMENTO são text no banco, então o formato não é
    garantido. Devolver None deixa o campo vazio em vez de mostrar a data de
    hoje, que pareceria um valor real e seria gravado como se fosse.
    """
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if not valor:
        return None
    texto = str(valor).strip()
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        pass
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto[:10], formato).date()
        except ValueError:
            continue
    return None


def desenha_campo(spec: dict, registro: dict, prefixo: str):
    """Desenha um campo já preenchido e devolve o valor atual do widget."""
    col, tipo, label = spec["col"], spec["tipo"], spec["label"]
    chave = f"{prefixo}_{col}"
    atual = registro.get(col)

    if tipo == "texto":
        return st.text_input(label, value="" if atual is None else str(atual), key=chave)
    if tipo == "texto_longo":
        return st.text_area(label, value="" if atual is None else str(atual), key=chave)
    if tipo == "inteiro":
        return int(
            st.number_input(
                label,
                value=para_int(atual),
                min_value=spec.get("minimo", 0),
                max_value=spec.get("maximo", 2_000_000_000),
                step=1,
                format="%d",
                key=chave,
            )
        )
    if tipo == "decimal":
        return float(
            st.number_input(
                label,
                value=para_float(atual),
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key=chave,
            )
        )
    if tipo == "mes":
        numero_mes = para_int(atual)
        indice = numero_mes - 1 if 1 <= numero_mes <= 12 else 0
        return MESES.index(st.selectbox(label, MESES, index=indice, key=chave)) + 1
    if tipo == "opcoes":
        opcoes = spec["opcoes"]
        indice = opcoes.index(atual) if atual in opcoes else 0
        return st.selectbox(label, opcoes, index=indice, key=chave)
    if tipo == "data":
        return st.date_input(label, value=para_data(atual), format="DD/MM/YYYY", key=chave)
    if tipo == "calculado":
        st.text_input(
            label,
            value="" if atual is None else str(atual),
            disabled=True,
            key=chave,
            help="calculado automaticamente",
        )
        return atual
    return atual


def mesma_coisa(antes, depois) -> bool:
    """Compara valor do banco com valor do widget sem falso positivo."""
    if isinstance(depois, (date, datetime)):
        return str(antes)[:10] == depois.isoformat()[:10]
    if isinstance(depois, float):
        try:
            return abs(float(antes or 0) - depois) < 1e-9
        except (TypeError, ValueError):
            return False
    if isinstance(depois, int):
        try:
            return int(antes or 0) == depois
        except (TypeError, ValueError):
            return False
    return ("" if antes is None else str(antes)) == ("" if depois is None else str(depois))


def salvar_edicao(tabela_app, id_registro, registro, mudancas, chave_msg, chave_versao) -> None:
    if not mudancas:
        st.session_state[chave_msg] = ("warning", "Nenhum campo foi alterado.")
        return
    ajuste = AJUSTES_EDICAO.get(tabela_app)
    if ajuste is not None:
        mudancas = ajuste(registro, mudancas)
    try:
        atualizar(tabela_app, id_registro, mudancas)
    except Exception as erro:
        st.session_state[chave_msg] = ("error", f"Não alterou: {erro}")
        return
    campos = ", ".join(sorted(mudancas))
    st.session_state[chave_msg] = ("success", f"Registro #{id_registro} atualizado ({campos}).")
    st.session_state[chave_versao] = st.session_state.get(chave_versao, 0) + 1


def pedir_exclusao(chave_conf, id_registro) -> None:
    st.session_state[chave_conf] = id_registro


def cancelar_exclusao(chave_conf) -> None:
    st.session_state.pop(chave_conf, None)


def confirmar_exclusao(tabela_app, id_registro, chave_conf, chave_msg, chave_versao) -> None:
    st.session_state.pop(chave_conf, None)
    try:
        excluir(tabela_app, id_registro)
    except Exception as erro:
        st.session_state[chave_msg] = ("error", f"Não excluiu: {erro}")
        return

    aviso = ""
    # anexos só saem depois que a linha some, para não perder o arquivo de um
    # registro que continuou no banco
    if tabela_app == "licencas":
        try:
            removidos = excluir_evidencias(id_registro)
            aviso = f" {removidos} anexo(s) removido(s) do MinIO."
        except Exception as erro:
            aviso = f" ATENÇÃO: a linha saiu, mas o anexo ficou no MinIO ({erro})."

    st.session_state[chave_msg] = ("success", f"Registro #{id_registro} excluído.{aviso}")
    st.session_state[chave_versao] = st.session_state.get(chave_versao, 0) + 1


def rotulo_registro(tabela_app: str, linha: dict) -> str:
    partes = []
    for col in RESUMO_REGISTRO.get(tabela_app, ()):
        valor = linha.get(col)
        if valor not in (None, ""):
            partes.append(str(valor)[:22])
    return f"#{linha.get('id')} · " + " · ".join(partes) if partes else f"#{linha.get('id')}"


def painel_edicao(tabela_app: str, limite: int = 200) -> None:
    """Aba de edição: lista, escolhe um registro, edita ou exclui."""
    chave_versao = f"ver_{tabela_app}"
    versao = st.session_state.setdefault(chave_versao, 0)
    chave_msg = f"msg_edicao_{tabela_app}"
    chave_conf = f"conf_exclusao_{tabela_app}"

    render_msg(chave_msg)

    try:
        df = listar_registros(tabela_app, limite)
    except Exception as erro:
        st.error(f"Não foi possível ler {TABELAS_DB[tabela_app]}: {erro}")
        return

    if df.empty:
        st.info(
            "Nenhum registro para editar. Se você acabou de gravar e nada "
            "aparece, é a RLS sem política de SELECT."
        )
        return

    st.dataframe(df, hide_index=True, height=240)
    st.caption(f"{len(df)} registro(s) mais recente(s).")

    if "id" not in df.columns:
        st.warning("A consulta não trouxe a coluna id — sem ela não há como editar.")
        return

    registros = df.to_dict("records")
    rotulos = {rotulo_registro(tabela_app, r): r for r in registros}

    st.divider()
    escolhido = st.selectbox(
        "Registro",
        list(rotulos),
        key=f"sel_{tabela_app}_{versao}",
        help="Escolha o lançamento que quer corrigir ou excluir",
    )
    registro = rotulos[escolhido]
    id_registro = registro["id"]

    # prefixo com id e versão: trocar de registro recria os widgets já
    # preenchidos com os valores daquela linha
    prefixo = f"ed_{tabela_app}_{versao}_{id_registro}"

    especificacao = CAMPOS_EDICAO.get(tabela_app, [])
    curtos = [c for c in especificacao if c["tipo"] != "texto_longo"]
    longos = [c for c in especificacao if c["tipo"] == "texto_longo"]

    valores = {}
    colunas = st.columns(3)
    for i, spec in enumerate(curtos):
        with colunas[i % 3]:
            valores[spec["col"]] = desenha_campo(spec, registro, prefixo)
    for spec in longos:
        valores[spec["col"]] = desenha_campo(spec, registro, prefixo)

    mudancas = {
        col: valor
        for col, valor in valores.items()
        if not mesma_coisa(registro.get(col), valor)
    }

    if tabela_app == "licencas":
        painel_evidencia(id_registro, versao)

    st.divider()
    if mudancas:
        st.caption("Alterado nesta tela: " + ", ".join(sorted(mudancas)))
    else:
        st.caption("Nenhuma alteração pendente.")

    esq, meio, _ = st.columns([1, 1, 2])
    with esq:
        st.button(
            "💾 Salvar alterações",
            key=f"btn_salvar_ed_{tabela_app}_{versao}",
            disabled=not mudancas,
            on_click=salvar_edicao,
            args=(tabela_app, id_registro, registro, mudancas, chave_msg, chave_versao),
        )
    with meio:
        st.button(
            "🗑️ Excluir",
            key=f"btn_excluir_{tabela_app}_{versao}",
            on_click=pedir_exclusao,
            args=(chave_conf, id_registro),
        )

    if st.session_state.get(chave_conf) == id_registro:
        st.warning(f"Excluir o registro **{escolhido}**? A ação não tem volta.")
        c1, c2, _ = st.columns([1, 1, 2])
        with c1:
            st.button(
                "Confirmar exclusão",
                key=f"btn_conf_{tabela_app}_{versao}",
                on_click=confirmar_exclusao,
                args=(tabela_app, id_registro, chave_conf, chave_msg, chave_versao),
            )
        with c2:
            st.button(
                "Cancelar",
                key=f"btn_cancel_{tabela_app}_{versao}",
                on_click=cancelar_exclusao,
                args=(chave_conf,),
            )


# ------------------------------------------------
# Evidência da licença (ver e substituir)
# ------------------------------------------------
def substituir_evidencia(id_registro, chave_upload, chave_msg, chave_versao) -> None:
    arquivo = st.session_state.get(chave_upload)
    if arquivo is None:
        st.session_state[chave_msg] = ("warning", "Escolha o novo arquivo antes de substituir.")
        return
    try:
        # apaga os antigos primeiro: a extensão pode mudar e sobrariam dois
        excluir_evidencias(id_registro)
        objeto = subir_evidencia(id_registro, arquivo)
    except Exception as erro:
        st.session_state[chave_msg] = ("error", f"Não substituiu: {erro}")
        return
    st.session_state[chave_msg] = ("success", f"Evidência substituída por {objeto}.")
    st.session_state[chave_versao] = st.session_state.get(chave_versao, 0) + 1


def painel_evidencia(id_registro, versao) -> None:
    st.markdown("**Evidência no MinIO**")
    manager = getattr(meu_minio, "manager", None)
    if manager is None:
        st.caption("MinIO indisponível — não foi possível listar o anexo.")
        return

    try:
        objetos = list(
            manager.client.list_objects(
                BUCKET_LICENCAS, prefix=f"{id_registro}_", recursive=True
            )
        )
    except Exception as erro:
        st.caption(f"Falha ao listar o anexo: {erro}")
        return

    if not objetos:
        st.warning("Este registro está sem evidência no bucket.")
    for obj in objetos:
        esq, dir_ = st.columns([3, 1])
        with esq:
            st.write(f"📎 `{obj.object_name}` · {(obj.size or 0) / 1024:,.1f} KB")
        with dir_:
            try:
                url = manager.generate_presigned_download_url(
                    BUCKET_LICENCAS, obj.object_name, expires_hours=1
                )
                st.link_button("Abrir", url)
            except Exception as erro:
                st.caption(f"sem link ({erro})")

    with st.expander("Substituir evidência"):
        chave_upload = f"sub_evid_{id_registro}_{versao}"
        st.file_uploader(
            "Novo arquivo",
            type=TIPOS_EVIDENCIA,
            key=chave_upload,
            help="Substitui o anexo atual; o antigo é apagado do bucket.",
        )
        st.button(
            "♻️ Substituir",
            key=f"btn_sub_evid_{id_registro}_{versao}",
            on_click=substituir_evidencia,
            args=(
                id_registro,
                chave_upload,
                f"msg_edicao_licencas",
                f"ver_licencas",
            ),
        )


def tela_consumos() -> None:
    cabecalho_tela("consumos")
    aba_novo, aba_editar = st.tabs(["➕ Novo lançamento", "✏️ Editar / Excluir"])
    with aba_novo:
        form_consumos()
    with aba_editar:
        painel_edicao("consumos")


def tela_licencas() -> None:
    cabecalho_tela("licencas")
    aba_novo, aba_editar = st.tabs(["➕ Novo lançamento", "✏️ Editar / Excluir"])
    with aba_novo:
        form_licencas()
    with aba_editar:
        painel_edicao("licencas")


def tela_custos() -> None:
    cabecalho_tela("custos")
    aba_novo, aba_editar = st.tabs(["➕ Novo lançamento", "✏️ Editar / Excluir"])
    with aba_novo:
        form_custos()
    with aba_editar:
        painel_edicao("custos")


def tela_reciclaveis() -> None:
    cabecalho_tela("reciclaveis")
    aba_novo, aba_editar = st.tabs(["➕ Novo lançamento", "✏️ Editar / Excluir"])
    with aba_novo:
        form_reciclaveis()
    with aba_editar:
        painel_edicao("reciclaveis")


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
