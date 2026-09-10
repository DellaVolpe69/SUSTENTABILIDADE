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

# CSS da tela de login. Depois do login cada tela injeta o seu (CSS_MENU ou
# CSS_INTERNO), então este fundo escuro deixou de ser global — carregá-lo em
# todas as telas só custava o download de uma imagem que não seria vista.
CSS_LOGIN = f"""
<style>
.stApp {{
    background: linear-gradient(rgba(0,0,0,0.7), rgba(0,0,0,0.7)),
        url("{url_imagem}");
    background-size: cover;
}}
header, [data-testid="stHeader"] {{ background: transparent; }}
</style>
"""

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

    st.markdown(CSS_LOGIN, unsafe_allow_html=True)

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

# A validação de acesso ficou mais abaixo, na seção PERFIL DE ACESSO:
# agora ela consulta SUSTENTABILIDADE_USUARIOS, e para isso o cliente do
# Supabase precisa existir. Aqui só garantimos que há um e-mail.
if not isinstance(user_email, str) or not user_email.strip():
    st.error("Não foi possível identificar seu e-mail no Azure AD.")
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

# Quantos registros as telas carregam. 1000 é o teto padrão do PostgREST
# no Supabase (db-max-rows): pedir mais não traz mais.
LIMITE_REGISTROS = 1000


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


def listar_registros(tabela_app: str, limite: int = LIMITE_REGISTROS) -> pd.DataFrame:
    """Lista os registros que o usuário logado pode ver.

    Admin vê tudo; os demais recebem um filtro por FILIAL. Todas as quatro
    tabelas têm essa coluna, então ela é o recorte único — sem isso um
    usuário de filial leria o lançamento das outras.
    """
    cliente = conectar_supabase()
    consulta = cliente.table(TABELAS_DB[tabela_app]).select("*")
    if not PERFIL["admin"]:
        consulta = consulta.in_("FILIAL", PERFIL["filiais"])
    resposta = consulta.order("id", desc=True).limit(limite).execute()
    return pd.DataFrame(resposta.data or [])


# ================================================
# PERFIL DE ACESSO (quem vê o quê)
# ================================================
# Duas classes de usuário:
#   - ADMINS (lista no código): veem todas as filiais.
#   - cadastrados em SUSTENTABILIDADE_USUARIOS: veem apenas a(s) filial(is)
#     da sua linha, e só conseguem lançar para ela.
#
# ATENÇÃO — este filtro é da APLICAÇÃO, não do banco. O login é Azure AD, e
# o Supabase não sabe quem está logado: a chave do app fala com o PostgREST
# sempre como o mesmo papel. Quem tiver a chave e a URL continua lendo tudo
# por fora do app. RLS de verdade por filial exigiria Supabase Auth (ou um
# JWT assinado com a filial no claim). Ver observação no fim do arquivo.

TABELA_USUARIOS = "SUSTENTABILIDADE_USUARIOS"

# Quem vê tudo. Reaproveita a lista que já existia no topo do arquivo.
ADMINS = {e.strip().lower() for e in USUARIOS_AUTORIZADOS}

# A tabela pode ter nomeado a coluna de e-mail de várias formas; em vez de
# adivinhar uma, procuramos entre os nomes plausíveis.
NOMES_EMAIL = {"USUARIO", "USUARIOS", "EMAIL", "EMAILS", "LOGIN", "USUARIOEMAIL"}
NOMES_FILIAL = {"FILIAL", "FILIAIS"}
NOMES_CNPJ = {"CNPJ", "CNPJS"}


def chave_simples(nome) -> str:
    """Nome de coluna sem espaço, underscore ou caixa — para comparar."""
    return "".join(ch for ch in str(nome).upper() if ch.isalnum())


def acha_coluna(colunas, nomes_aceitos):
    for coluna in colunas:
        if chave_simples(coluna) in nomes_aceitos:
            return coluna
    return None


@st.cache_data(ttl=300, show_spinner=False)
def carregar_usuarios() -> pd.DataFrame:
    """Cache de 5 min: usuário novo passa a valer sem reiniciar o app."""
    cliente = conectar_supabase()
    resposta = cliente.table(TABELA_USUARIOS).select("*").execute()
    return pd.DataFrame(resposta.data or [])


def valores_limpos(serie) -> list:
    vistos = set()
    for bruto in serie.dropna():
        texto = str(bruto).strip()
        if texto:
            vistos.add(texto.upper())
    return sorted(vistos)


def perfil_acesso(email: str) -> dict:
    """Devolve o que este e-mail pode ver."""
    email = (email or "").strip().lower()
    admin = email in ADMINS
    perfil = {
        "email": email,
        "admin": admin,
        "ok": admin,
        "filiais": [],
        "cnpjs": [],
        "erro": None,
    }

    try:
        df = carregar_usuarios()
    except Exception as erro:
        perfil["erro"] = f"não foi possível ler {TABELA_USUARIOS}: {erro}"
        return perfil

    if df.empty:
        perfil["erro"] = (
            f"{TABELA_USUARIOS} voltou vazia — tabela sem linhas ou RLS sem "
            "política de SELECT"
        )
        return perfil

    col_email = acha_coluna(df.columns, NOMES_EMAIL)
    col_filial = acha_coluna(df.columns, NOMES_FILIAL)
    col_cnpj = acha_coluna(df.columns, NOMES_CNPJ)

    if col_email is None or col_filial is None:
        perfil["erro"] = (
            f"{TABELA_USUARIOS} precisa de uma coluna de e-mail e uma de FILIAL. "
            f"Colunas encontradas: {list(df.columns)}"
        )
        return perfil

    iguais = df[col_email].astype(str).str.strip().str.lower() == email
    minhas = df[iguais]
    # o usuário pode ter mais de uma linha, uma por filial
    perfil["filiais"] = valores_limpos(minhas[col_filial])
    if col_cnpj is not None:
        perfil["cnpjs"] = valores_limpos(minhas[col_cnpj])

    if not admin:
        perfil["ok"] = bool(perfil["filiais"])
    return perfil


def filiais_cadastradas() -> list:
    """Lista mestra de filiais: a coluna FILIAL da tabela de usuários."""
    try:
        df = carregar_usuarios()
    except Exception:
        return []
    if df.empty:
        return []
    coluna = acha_coluna(df.columns, NOMES_FILIAL)
    return valores_limpos(df[coluna]) if coluna is not None else []


def opcoes_filial() -> list:
    """Admin escolhe qualquer filial; os demais, só a(s) sua(s)."""
    return filiais_cadastradas() if PERFIL["admin"] else PERFIL["filiais"]


def entrada_filial(chave: str, label: str = "FILIAL") -> None:
    """Campo FILIAL como lista fechada, com texto livre como último recurso."""
    opcoes = opcoes_filial()
    if not opcoes:
        st.text_input(
            label,
            key=chave,
            help=f"{TABELA_USUARIOS} não devolveu filiais — digite manualmente",
        )
        return
    st.selectbox(label, opcoes, key=chave)


# ------------------------------------------------
# Porteiro: aqui o acesso é decidido
# ------------------------------------------------
PERFIL = perfil_acesso(usuario_email_logado)

if not PERFIL["ok"]:
    st.error(
        "Acesso não autorizado. Seu e-mail não está na lista do painel nem "
        f"cadastrado em {TABELA_USUARIOS} com uma filial."
    )
    if PERFIL["erro"]:
        st.caption(f"Detalhe técnico: {PERFIL['erro']}")
    st.caption(f"E-mail identificado: {PERFIL['email']}")
    st.stop()


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
    valor = st.session_state.get(chave)
    return "" if valor is None else str(valor).strip()


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
# TEMA CLARO (sem config.toml)
# ================================================
# O Streamlit escolhe o tema pela preferência do VISITANTE: quem está com o
# sistema em modo escuro recebe widgets escuros, e o CSS das telas não
# alcança o interior deles (menu do selectbox, calendário, popover de ajuda).
# O jeito canônico de travar isso é .streamlit/config.toml — que é um
# ARQUIVO SEPARADO. Como o app é distribuído como um .py único, o tema é
# forçado aqui.
#
# color-scheme é o que faz o navegador desenhar scrollbar e controles
# nativos na versão clara; sem ele sobram detalhes escuros.

CSS_BASE_CLARA = """
<style>
:root, .stApp { color-scheme: light !important; }

[data-testid="stAppViewContainer"] { color: #2C3A32; }
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] span,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] li { color: #3C4B42; }

/* menu do selectbox, calendário do date_input e popovers de ajuda: ficam
   fora do container da página, então precisam de regra própria */
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul[role="listbox"],
[data-baseweb="calendar"],
[data-baseweb="datepicker"] {
    background: #FFFFFF !important;
    color: #2C3A32 !important;
    border: 1px solid #DCE5DD !important;
}
[role="option"] { color: #2C3A32 !important; background: transparent !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] {
    background: #EAF3EC !important; color: #14532D !important;
}
[data-baseweb="calendar"] [aria-selected="true"] {
    background: #1F7A3D !important; color: #FFFFFF !important;
}
[data-baseweb="tooltip"] { background: #14532D !important; color: #FFFFFF !important; }

/* mensagens de estado: st.success / st.warning / st.error / st.info */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* barra de rolagem no tom do painel */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #C9DACE; border-radius: 6px; }
::-webkit-scrollbar-track { background: transparent; }
</style>
"""

st.markdown(CSS_BASE_CLARA, unsafe_allow_html=True)


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


# ================================================
# TELA INICIAL (MENU) — identidade ESG
# ================================================
# A arte de fundo já traz logo, selo ESG e as formas verdes embutidos, então
# aqui vai só o conteúdo por cima dela.
#
# Cada card é montado em duas partes: o topo (ícone, título e descrição) é
# HTML, e o rodapé é um st.button de verdade, colado por baixo pelo CSS.
# A primeira versão usava o card inteiro como <a href="?tela=...">, o que
# ficava idêntico ao layout — mas o link recarrega a página, o Streamlit
# abre uma sessão nova, o token do Azure guardado em st.session_state se
# perde e o login era pedido de novo a cada clique.

URL_FUNDO_MENU = (
    "https://raw.githubusercontent.com/DellaVolpe69/Images/main/SUSTENTABILIDADE.png"
)
URL_LOGO_COLORIDO = "https://raw.githubusercontent.com/DellaVolpe69/Images/main/logo.png"

VERDE = "#1F7A3D"
VERDE_ESCURO = "#14532D"
LARANJA = "#E4610A"

# ícones desenhados aqui em SVG: o mockup usa um conjunto próprio que não
# está no repositório de imagens. currentColor faz cada um herdar a cor do
# seu card.
SVG_RECICLAR = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M7.5 4.5 12 4.5 9.8 8.3"/><path d="M12 4.5 9.8 8.3"/>'
    '<path d="M4.2 15.5 2 11.7l4.4-.1"/><path d="M6.4 11.6 2 11.7"/>'
    '<path d="M19.8 15.5 22 11.7l-4.4-.1"/>'
    '<path d="M5.2 17.5h5.1l-2.2 3.8"/><path d="M18.8 17.5h-5.1l2.2 3.8"/>'
    '<path d="M12 4.5 16.4 12"/><path d="M7.6 12 3.2 19.5"/>'
    '<path d="M16.4 12l4.4 7.5"/></svg>'
)
SVG_DOCUMENTO = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/></svg>'
)
SVG_MOEDAS = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<ellipse cx="12" cy="6.5" rx="6.5" ry="2.6"/>'
    '<path d="M5.5 6.5v4c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-4"/>'
    '<path d="M5.5 10.5v4c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-4"/>'
    '<path d="M12 17.1v2.4"/><path d="M9.6 19.5h4.8"/></svg>'
)
SVG_LIXEIRA = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'
    '<path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/>'
    '<path d="M10.5 11.5v6"/><path d="M13.5 11.5v6"/></svg>'
)
SVG_GRAFICO = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 20h16"/><path d="M6.5 20v-6"/><path d="M11 20V9"/>'
    '<path d="M15.5 20v-8"/><path d="M20 20V5"/></svg>'
)
SVG_FOLHA = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20 4c0 9-5 14-11 14-2 0-4-1-4-1S6 6 20 4z"/>'
    '<path d="M5 21c1-6 4-10 9-13"/></svg>'
)
SVG_PESSOAS = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/>'
    '<circle cx="17" cy="9.5" r="2.3"/><path d="M15 14.6c3 .2 5.5 2 5.5 4.4"/></svg>'
)
SVG_ESCUDO = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 3l7 3v6c0 4.2-2.9 7.6-7 9-4.1-1.4-7-4.8-7-9V6z"/>'
    '<path d="M9 12l2.2 2.2L15.5 10"/></svg>'
)
SVG_GOTA = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 3.5c3.4 4 5.5 6.7 5.5 9.4a5.5 5.5 0 0 1-11 0c0-2.7 2.1-5.4 5.5-9.4z"/>'
    '</svg>'
)

PILARES = [
    (SVG_FOLHA, "AMBIENTAL", VERDE,
     "Cuidamos do meio ambiente hoje para preservar o amanhã."),
    (SVG_PESSOAS, "SOCIAL", LARANJA,
     "Valorizamos pessoas, promovemos segurança e desenvolvimento comunidades."),
    (SVG_ESCUDO, "GOVERNANÇA", VERDE,
     "Atuamos com ética, transparência e responsabilidade em todas as nossas relações."),
]

CARDS_MENU = [
    ("consumos", "CONSUMOS E<br>SERVIÇOS", SVG_RECICLAR, "verde",
     "Acompanhe os consumos e serviços relacionados à sustentabilidade."),
    ("licencas", "CONTROLE DE<br>LICENÇAS", SVG_DOCUMENTO, "laranja",
     "Gerencie e acompanhe as licenças e documentações ambientais."),
    ("custos", "CUSTOS E<br>ORÇAMENTOS", SVG_MOEDAS, "laranja",
     "Visualize custos, orçamentos e investimentos em iniciativas sustentáveis."),
    ("reciclaveis", "RECICLÁVEIS", SVG_LIXEIRA, "verde",
     "Acompanhe a gestão de resíduos e o destino dos materiais recicláveis."),
    ("indicador", "INDICADOR<br>SUSTENTABILIDADE", SVG_GRAFICO, "verde",
     "Indicadores de desempenho ESG para uma gestão mais eficiente."),
]

RODAPE_ITENS = [
    (SVG_FOLHA, "Menos Emissões"),
    (SVG_RECICLAR, "Uso Consciente<br>de Recursos"),
    (SVG_GOTA, "Preservação<br>da Água"),
    (SVG_PESSOAS, "Pessoas e Comunidades<br>em Primeiro Lugar"),
    (SVG_ESCUDO, "Ética e<br>Transparência"),
]

CSS_MENU = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

/* A arte entra inteira (100% auto, sem recorte) e presa ao viewport:
   assim ela acompanha o zoom junto com o conteúdo, em vez de ficar parada
   enquanto os cards crescem. Sem degradê por cima — a arte já traz a área
   creme à esquerda, o logo, o selo ESG e as formas verdes. */
.stApp {
    background:
        url("URL_DO_FUNDO") top center / 100% auto no-repeat fixed,
        #FAFAF7 !important;
}
header, [data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { right: 1rem; }

/* conteúdo encostado à esquerda, como no layout aprovado: o Streamlit
   centraliza o block-container por padrão, e era isso que jogava o painel
   para o meio da tela */
.block-container {
    max-width: 100% !important;
    /* 8vw acompanha o logo, que escala com a largura; +30px de respiro */
    padding: calc(8vw + 30px) 2.5rem 2rem 3.2rem !important;
}
.dv-menu { max-width: min(1180px, 100%); }
/* o título precisa de largura própria, senão os pilares o comprimem a
   zero; nowrap impede a quebra feia de "Sustentabilidade" */
.dv-menu .dv-cabecalho > div:first-child { flex: 0 1 430px; min-width: 300px; }
.dv-menu .dv-titulo { white-space: nowrap; }

/* card e botão são dois elementos do Streamlit: sem zerar o espaço entre
   eles ficaria uma fenda no meio do card. Vale para a tela toda porque
   este CSS só é injetado no menu. */
[data-testid="stVerticalBlock"] { gap: 0 !important; }

.dv-menu, .dv-menu * { font-family: 'Poppins', 'Segoe UI', sans-serif; }
.dv-menu { color: #3C4B42; }

/* ---------- cabeçalho ---------- */
.dv-menu .dv-cabecalho {
    display: flex; flex-wrap: wrap; gap: 26px 56px;
    align-items: flex-start; justify-content: space-between;
    margin: 0 0 12px;
}
.dv-menu .dv-eyebrow {
    font-size: 1.35rem !important; font-weight: 300 !important;
    color: #52645A !important; margin: 0; line-height: 1.1;
}
.dv-menu .dv-titulo {
    font-size: 2.7rem !important; font-weight: 700 !important;
    color: #1F7A3D !important; margin: -2px 0 10px; line-height: 1.05;
    letter-spacing: -0.5px;
}
.dv-menu .dv-bemvindo {
    font-size: 0.9rem !important; color: #52645A !important; margin: 0 0 10px;
}
.dv-menu .dv-bemvindo a { color: #E4610A !important; text-decoration: none; }
.dv-menu .dv-acesso {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: 0.8rem !important; color: #52645A !important; margin: 0;
    background: rgba(255,255,255,0.8); border: 1px solid #DCE5DD;
    border-radius: 999px; padding: 5px 13px;
}
.dv-menu .dv-acesso svg { width: 15px; height: 15px; color: #1F7A3D; }

/* ---------- pilares ESG ---------- */
.dv-menu .dv-pilares { display: flex; gap: 26px; flex-wrap: wrap; padding-top: 6px; }
.dv-menu .dv-pilar { display: flex; gap: 10px; max-width: 185px; }
.dv-menu .dv-pilar-bolha {
    flex: 0 0 auto; width: 36px; height: 36px; border-radius: 50%;
    display: grid; place-items: center; background: #EAF3EC;
}
.dv-menu .dv-pilar-bolha svg { width: 20px; height: 20px; }
.dv-menu .dv-pilar h4 {
    font-size: 0.78rem !important; font-weight: 700 !important;
    letter-spacing: 0.06em; margin: 2px 0 3px;
}
.dv-menu .dv-pilar p {
    font-size: 0.7rem !important; line-height: 1.4;
    color: #6B7A70 !important; margin: 0;
}

/* ---------- chamada ---------- */
.dv-menu .dv-compromisso {
    font-size: 1.3rem !important; font-weight: 300 !important;
    color: #52645A !important; margin: 2px 0 14px; line-height: 1.25;
}
.dv-menu .dv-compromisso b { color: #E4610A !important; font-weight: 600 !important; }

/* ---------- cards ---------- */
/* o topo do card é HTML; o rodapé é um st.button de verdade, colado por
   baixo. Navegação por botão (e não por link) é o que preserva a sessão —
   um <a href> recarrega a página e o login do Azure se perde. */
.dv-cardtopo {
    background: rgba(255,255,255,0.96);
    border: 1px solid #E3EAE4; border-bottom: none;
    border-radius: 14px 14px 0 0;
    /* 18px embaixo: com 8px a descrição encostava no rodapé do card e o
       botão, opaco, cobria a metade de baixo das letras */
    padding: 15px 18px 18px;
    min-height: 124px; overflow: visible;
}
.dv-cardtopo .dv-card-topo { display: flex; gap: 13px; align-items: flex-start; }
.dv-cardtopo .dv-card-bolha {
    flex: 0 0 auto; width: 42px; height: 42px; border-radius: 50%;
    display: grid; place-items: center; background: #EAF3EC; color: #1F7A3D;
}
.dv-cardtopo.laranja .dv-card-bolha { background: #FDEEE3; color: #E4610A; }
.dv-cardtopo .dv-card-bolha svg { width: 23px; height: 23px; }
.dv-cardtopo h3 {
    font-size: 0.84rem !important; font-weight: 700 !important;
    letter-spacing: 0.04em; color: #1F7A3D !important; margin: 2px 0 6px;
    line-height: 1.25;
}
.dv-cardtopo.laranja h3 { color: #E4610A !important; }
.dv-cardtopo p {
    font-size: 0.76rem !important; line-height: 1.5;
    color: #6B7A70 !important; margin: 0 !important;
}

/* rodapé clicável do card */
div[data-testid="stButton"] button {
    background: rgba(255,255,255,0.96) !important;
    color: #1F7A3D !important;
    border: 1px solid #E3EAE4 !important; border-top: none !important;
    border-radius: 0 0 14px 14px !important;
    width: 100% !important; padding: 0.5em 1.1em !important;
    font-weight: 600 !important; font-size: 0.76rem !important;
    letter-spacing: 0.04em;
    justify-content: flex-end !important; text-align: right !important;
    box-shadow: none !important; transition: 0.15s ease;
    margin-bottom: 14px !important;
}
div[data-testid="stButton"] button:hover {
    background: #EAF3EC !important; border-color: #1F7A3D !important;
    color: #14532D !important; transform: none !important;
}
/* o rótulo vem embrulhado em <p>/<div>: sem isto ele ignora a cor do botão */
div[data-testid="stButton"] button * { color: inherit !important; }
/* cor por card: só funciona nas versões do Streamlit que expõem st-key-*.
   Onde não existir, o rodapé fica verde — sem quebrar nada. */
.st-key-card_licencas button, .st-key-card_custos button { color: #E4610A !important; }
.st-key-card_licencas button:hover, .st-key-card_custos button:hover {
    background: #FDEEE3 !important; border-color: #E4610A !important;
    color: #B84E08 !important;
}

/* ---------- faixa de compromissos ---------- */
.dv-menu .dv-faixa {
    background: rgba(255,255,255,0.94); border: 1px solid #E3EAE4;
    border-radius: 16px; padding: 12px 18px 14px;
    max-width: min(760px, 100%); margin-top: 22px;
}
.dv-menu .dv-faixa-titulo {
    text-align: center; font-size: 0.88rem !important; font-weight: 600 !important;
    letter-spacing: 0.05em; color: #14532D !important; margin: 0 0 12px;
}
.dv-menu .dv-faixa-titulo b { color: #E4610A !important; font-weight: 700 !important; }
.dv-menu .dv-faixa-itens {
    display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
}
.dv-menu .dv-faixa-item { text-align: center; flex: 1 1 110px; color: #1F7A3D; }
.dv-menu .dv-faixa-item svg { width: 25px; height: 25px; }
.dv-menu .dv-faixa-item span {
    display: block; margin-top: 5px; font-size: 0.67rem !important;
    line-height: 1.3; color: #6B7A70 !important;
}

/* ---------- telas estreitas ---------- */
/* A arte é 16:9: encolhida, o caminhão avança sobre o texto e o logo fica
   ilegível. Abaixo de 980px ela sai e entra só o logo no canto. */
@media (max-width: 980px) {
    .stApp {
        background:
            url("URL_DO_LOGO") 22px 18px / 160px auto no-repeat,
            #FAFAF7 !important;
    }
    .block-container { padding: 5.5rem 1.2rem 2rem 1.2rem !important; }
    .dv-menu .dv-titulo { white-space: normal; }
    .dv-menu .dv-titulo { font-size: 2.1rem !important; }
}
</style>
"""


def html_cabecalho() -> str:
    escopo = (
        "todas as filiais"
        if PERFIL["admin"]
        else ", ".join(PERFIL["filiais"]) or "nenhuma filial"
    )
    return (
        '<div class="dv-menu">'
        '<div class="dv-cabecalho"><div>'
        '<p class="dv-eyebrow">Painel de</p>'
        '<h1 class="dv-titulo">Sustentabilidade</h1>'
        f'<p class="dv-bemvindo">Bem-vindo(a), {user_name} — '
        f'<a href="mailto:{usuario_email_logado}">{usuario_email_logado}</a></p>'
        f'<p class="dv-acesso">{SVG_PESSOAS} Acesso: {escopo}</p>'
        "</div>"
        f"{html_pilares()}"
        "</div>"
        '<p class="dv-compromisso">Nosso compromisso,<br><b>nosso caminho.</b></p>'
        "</div>"
    )


def html_card_topo(titulo: str, icone: str, cor: str, descricao: str) -> str:
    return (
        f'<div class="dv-cardtopo {cor}"><div class="dv-card-topo">'
        f'<div class="dv-card-bolha">{icone}</div>'
        f"<div><h3>{titulo}</h3><p>{descricao}</p></div>"
        "</div></div>"
    )


def tela_menu() -> None:
    estilo = CSS_MENU.replace("URL_DO_FUNDO", URL_FUNDO_MENU).replace(
        "URL_DO_LOGO", URL_LOGO_COLORIDO
    )
    st.markdown(estilo, unsafe_allow_html=True)

    url_sb, key_sb = credenciais_supabase()
    if not url_sb or not key_sb:
        st.error(
            "SUPABASE_URL e/ou SUPABASE_KEY não encontrados em st.secrets — "
            "nenhuma tela vai gravar."
        )

    st.markdown(html_cabecalho(), unsafe_allow_html=True)

    # a terceira coluna é só respiro: mantém os cards na área clara, sem
    # avançar sobre o caminhão
    col_a, col_b, _respiro = st.columns([1, 1, 1.5], gap="small")
    for i, (tela, titulo, icone, cor, descricao) in enumerate(CARDS_MENU):
        with col_a if i % 2 == 0 else col_b:
            st.markdown(html_card_topo(titulo, icone, cor, descricao), unsafe_allow_html=True)
            st.button(
                "Acessar  →",
                key=f"card_{tela}",
                on_click=ir_para,
                args=(tela,),
                use_container_width=True,
            )

    st.markdown('<div class="dv-menu">' + html_rodape() + "</div>", unsafe_allow_html=True)


def html_pilares() -> str:
    partes = []
    for icone, nome, cor, texto in PILARES:
        partes.append(
            '<div class="dv-pilar">'
            f'<div class="dv-pilar-bolha" style="color:{cor}">{icone}</div>'
            f'<div><h4 style="color:{cor}">{nome}</h4><p>{texto}</p></div>'
            "</div>"
        )
    return '<div class="dv-pilares">' + "".join(partes) + "</div>"


def html_rodape() -> str:
    itens = "".join(
        f'<div class="dv-faixa-item">{icone}<span>{texto}</span></div>'
        for icone, texto in RODAPE_ITENS
    )
    return (
        '<div class="dv-faixa">'
        '<p class="dv-faixa-titulo">JUNTOS, <b>MOVEMOS</b> UM FUTURO MELHOR.</p>'
        f'<div class="dv-faixa-itens">{itens}</div>'
        "</div>"
    )


CSS_INTERNO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

/* Fundo claro nas telas de lançamento: sem a foto, que competiria com o
   formulário. A faixa verde no topo mantém a identidade do menu. */
.stApp {
    background: #F6F8F4 !important;
}
.stApp::before {
    content: ""; position: fixed; top: 0; left: 0; right: 0; height: 5px;
    background: linear-gradient(90deg, #1F7A3D 0%, #3F9D5A 55%, #E4610A 100%);
    z-index: 999;
}
header, [data-testid="stHeader"] { background: transparent !important; }
.block-container { padding-top: 2.6rem !important; max-width: 1250px; }

html, body, [class*="css"], .stMarkdown, label, input, textarea, select,
button, .stSelectbox, [data-testid="stMetricValue"] {
    font-family: 'Poppins', 'Segoe UI', sans-serif !important;
}

/* títulos das telas */
.stMarkdown h2 {
    color: #1F7A3D !important; font-weight: 700 !important;
    letter-spacing: -0.3px; font-size: 1.55rem !important;
}
.stMarkdown h3, .stMarkdown h4 { color: #14532D !important; font-weight: 600 !important; }
.stMarkdown p, .stMarkdown li, [data-testid="stCaptionContainer"] { color: #4A5A50; }
hr { border-color: #DCE5DD !important; }

/* rótulos de campo — forçados porque o visitante pode estar no tema escuro */
label, [data-testid="stWidgetLabel"] p {
    color: #3C4B42 !important; font-size: 0.78rem !important;
    font-weight: 600 !important; letter-spacing: 0.02em;
}

/* campos */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
    background: #FFFFFF !important;
    border-color: #DCE5DD !important;
    border-radius: 9px !important;
}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-baseweb="select"] div { color: #2C3A32 !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {
    border-color: #1F7A3D !important; box-shadow: 0 0 0 2px rgba(31,122,61,0.12) !important;
}

/* abas */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 4px; background: transparent; border-bottom: 1px solid #DCE5DD;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    background: transparent !important; border-radius: 9px 9px 0 0;
    padding: 8px 16px !important; color: #6B7A70 !important;
    font-weight: 600 !important; font-size: 0.84rem !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: #FFFFFF !important; color: #1F7A3D !important;
    border: 1px solid #DCE5DD !important; border-bottom-color: #FFFFFF !important;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: #1F7A3D !important; }

/* botões: o estilo antigo era um bloco escuro de largura total, feito para
   os tiles do menu antigo — que não existem mais */
div[data-testid="stButton"] button {
    background: #FFFFFF !important; color: #1F7A3D !important;
    border: 1px solid #C9DACE !important; border-radius: 10px !important;
    padding: 0.45em 1.1em !important; width: auto !important;
    font-weight: 600 !important; font-size: 0.84rem !important;
    box-shadow: none !important; transition: 0.15s ease;
}
div[data-testid="stButton"] button:hover {
    background: #EAF3EC !important; border-color: #1F7A3D !important;
    transform: none !important;
}
/* o rótulo é um <p> dentro do <button>: sem herdar, ele fica preto sobre o
   verde do botão primário */
div[data-testid="stButton"] button * { color: inherit !important; }
div[data-testid="stButton"] button[kind="primary"],
div[data-testid="stButton"] button[kind="primary"] * {
    background: #1F7A3D !important; color: #FFFFFF !important;
    border-color: #1F7A3D !important;
}
div[data-testid="stButton"] button[kind="primary"] * { background: none !important; }
div[data-testid="stButton"] button[kind="primary"]:hover,
div[data-testid="stButton"] button[kind="primary"]:hover * {
    background: #14532D !important; border-color: #14532D !important;
    color: #FFFFFF !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover * { background: none !important; }
div[data-testid="stButton"] button:disabled,
div[data-testid="stButton"] button:disabled * {
    background: #F1F4F1 !important; color: #A9B5AD !important;
    border-color: #E3EAE4 !important;
}
div[data-testid="stButton"] button:disabled * { background: none !important; }
div[data-testid="stButton"] button:focus-visible {
    outline: 2px solid #E4610A !important; outline-offset: 2px;
}

/* cartões de indicador: st.metric não aceita cor por cartão, então estes
   são HTML — dá para pintar fundo, faixa lateral e o número */
.dv-kpi {
    background: #FFFFFF; border: 1px solid #DCE5DD;
    border-left: 4px solid #C9DACE; border-radius: 12px;
    padding: 12px 14px; min-height: 88px;
    display: flex; flex-direction: column; gap: 2px;
}
.dv-kpi.verde {
    border-left-color: #1F7A3D;
    background: linear-gradient(180deg, #F4FAF5 0%, #FFFFFF 70%);
}
.dv-kpi.laranja {
    border-left-color: #E4610A;
    background: linear-gradient(180deg, #FFF6F0 0%, #FFFFFF 70%);
}
/* vencido é problema, não aviso: cor própria */
.dv-kpi.vermelho {
    border-left-color: #B3261E;
    background: linear-gradient(180deg, #FDF0EF 0%, #FFFFFF 70%);
}
.dv-kpi.vermelho strong { color: #8C1D18 !important; }
.dv-kpi-rotulo {
    font-size: 0.68rem !important; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #6B7A70 !important;
}
.dv-kpi strong {
    font-size: 1.35rem; font-weight: 700; color: #14532D !important;
    line-height: 1.2;
}
.dv-kpi.laranja strong { color: #B84E08 !important; }
.dv-kpi-nota { font-size: 0.66rem !important; color: #8A968E !important; }

/* barra lateral de páginas (tela de indicadores) */
[data-testid="stSidebar"] {
    background: #FFFFFF !important; border-right: 1px solid #DCE5DD;
}
[data-testid="stSidebar"] .dv-sidebar-titulo {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #6B7A70; margin: 0 0 10px;
}
/* itens de navegação: texto à esquerda, como lista, não como botão */
[data-testid="stSidebar"] div[data-testid="stButton"] button {
    justify-content: flex-start !important; text-align: left !important;
    border-radius: 8px !important; font-size: 0.82rem !important;
    padding: 0.45em 0.8em !important; margin-bottom: 3px !important;
}

/* tabela */
[data-testid="stDataFrame"] {
    border: 1px solid #DCE5DD !important; border-radius: 10px; overflow: hidden;
}

/* mensagens e blocos */
[data-testid="stMetric"] {
    background: #FFFFFF; border: 1px solid #DCE5DD; border-radius: 12px;
    padding: 10px 14px;
}
[data-testid="stMetricValue"] { color: #1F7A3D !important; }
[data-testid="stExpander"] {
    background: #FFFFFF; border: 1px solid #DCE5DD !important; border-radius: 10px;
}
[data-testid="stFileUploaderDropzone"] {
    background: #FFFFFF !important; border: 1px dashed #C9DACE !important;
}
</style>
"""


def cabecalho_tela(chave: str) -> None:
    """Título da tela + botão de retorno ao menu.

    Também injeta o CSS interno: toda tela de lançamento passa por aqui.
    """
    st.markdown(CSS_INTERNO, unsafe_allow_html=True)

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
        entrada_filial("con_filial")
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

    st.markdown("**Valores pagos por serviço (R$)**")
    st.caption("Todos os campos abaixo são valor em reais, não quantidade.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input("SÓLIDOS CONTAMINADOS (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_solidos")
        st.number_input("ENERGIA (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_energia")
        st.number_input("RECICLÁVEIS (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_reciclaveis")
    with c2:
        st.number_input("ÓLEO LUBRIFICANTE (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_oleo")
        st.number_input("COMUM (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_comum")
        st.number_input("CO² (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_co2")
    with c3:
        st.number_input("ÁGUA (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_agua")
        st.number_input("MADEIRA (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_madeira")

    st.button("💾 Salvar", key="btn_salvar_con", on_click=salvar_consumo, type="primary")
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
        entrada_filial("lic_filial")
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

    st.button(
        "💾 Salvar",
        key="btn_salvar_lic",
        on_click=salvar_licenca,
        disabled=arquivo is None,
        type="primary",
    )
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
        "MES": st.session_state.get("cus_mes", MESES[date.today().month - 1]),
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
        entrada_filial("cus_filial")
        st.text_input("MIGO", key="cus_migo")
        st.selectbox("MÊS", MESES, index=date.today().month - 1, key="cus_mes")
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

    st.button("💾 Salvar", key="btn_salvar_cus", on_click=salvar_custo, type="primary")
    render_msg("msg_custos")


# ================================================
# 4) RECICLÁVEIS  ->  SUSTENTABILIDADE_RECICLAVEIS
# ================================================
# Sem st.form também porque o TOTAL (PESO x VALOR/KG) precisa acompanhar a
# digitação — dentro de um form só haveria rerun no submit.
CAMPOS_RECICLAVEIS = (
    "rec_filial",
    "rec_material",
    "rec_material_novo",
    "rec_peso",
    "rec_valor_kg",
    "rec_pagamento",
)
OPCOES_PAGAMENTO = ["Pg Recebido", "Aguardando Pagamento"]

# Lista CURADA, não lida do banco: ler os valores existentes manteria TUBO e
# TUBOS como opções distintas e não padronizaria nada. Levantada dos 411
# lançamentos importados + MADEIRA, que entrou depois pelo app.
#
# Decisões embutidas (ver conversa de 10/09/2026):
#   * TUBOS foi unificado em TUBO (104 + 9 = 113 lançamentos)
#   * "SOBRA DE 2023" ficou fora: é ajuste de fechamento, não material
#   * "PAPEL" puro ficou fora: 1 lançamento, provavelmente um dos outros três
# Registro antigo com nome fora desta lista continua aparecendo na aba de
# edição — o campo do tipo "opcoes" inclui o valor gravado na lista.
MATERIAL_OUTRO = "OUTRO — digitar"
MATERIAIS_RECICLAVEIS = [
    "COBRE",
    "FERRO",
    "IBC VAZIO",
    "LATINHA",
    "MADEIRA",
    "METAL",
    "PAPEL ARQUIVO",
    "PAPEL BRANCO",
    "PAPEL ESCRITORIO",
    "PAPELÃO",
    "PLASTICO BRANCO",
    "PLASTICO COLORIDO",
    "PLASTICO DURO",
    "PLASTICO STRETCH",
    "SWA",
    "TAMBOR VAZIO",
    "TANQUE DE OLEO VELHO",
    "TUBO",
]


def material_reciclavel() -> str:
    """O material escolhido, ou o digitado quando a opção é OUTRO."""
    escolhido = txt("rec_material")
    if escolhido == MATERIAL_OUTRO:
        return txt("rec_material_novo").upper()
    return escolhido.upper()


def salvar_reciclaveis() -> None:
    faltando = []
    if not txt("rec_filial"):
        faltando.append("FILIAL")
    if not material_reciclavel():
        faltando.append("MATERIAL")
    if faltando:
        st.session_state["msg_reciclaveis"] = ("warning", "Obrigatório: " + ", ".join(faltando))
        return

    peso = float(st.session_state.get("rec_peso", 0.0))
    valor_kg = float(st.session_state.get("rec_valor_kg", 0.0))
    dados = {
        "FILIAL": txt("rec_filial").upper(),
        "DATA": st.session_state.get("rec_data", date.today()),
        "MATERIAL": material_reciclavel(),
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
        entrada_filial("rec_filial")
        st.date_input("DATA", value=date.today(), format="DD/MM/YYYY", key="rec_data")
        peso = st.number_input("PESO", min_value=0.0, step=0.01, format="%.2f", key="rec_peso")
    with c2:
        escolha = st.selectbox(
            "MATERIAL",
            MATERIAIS_RECICLAVEIS + [MATERIAL_OUTRO],
            key="rec_material",
            help="Lista fechada para o nome não variar entre lançamentos",
        )
        if escolha == MATERIAL_OUTRO:
            st.text_input(
                "Qual material?",
                key="rec_material_novo",
                placeholder="nome do material novo",
            )
        valor_kg = st.number_input(
            "VALOR/KG", min_value=0.0, step=0.01, format="%.2f", key="rec_valor_kg"
        )
    with c3:
        st.selectbox("PAGAMENTO", OPCOES_PAGAMENTO, key="rec_pagamento")
        st.metric("TOTAL", fmt_brl(peso * valor_kg))

    st.button("💾 Salvar", key="btn_salvar_rec", on_click=salvar_reciclaveis, type="primary")
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
        campo("FILIAL", "filial"),
        campo("ANO", "inteiro", minimo=1990, maximo=2100),
        campo("MES", "mes", "MÊS"),
        campo(COL_SOLIDOS, "decimal", "SÓLIDOS CONTAMINADOS (R$)"),
        campo(COL_OLEO, "decimal", "ÓLEO LUBRIFICANTE (R$)"),
        campo("AGUA", "decimal", "ÁGUA (R$)"),
        campo("ENERGIA", "decimal", "ENERGIA (R$)"),
        campo("COMUM", "decimal", "COMUM (R$)"),
        campo("MADEIRA", "decimal", "MADEIRA (R$)"),
        campo("RECICLAVEIS", "decimal", "RECICLÁVEIS (R$)"),
        campo("CO2", "decimal", "CO² (R$)"),
    ],
    "licencas": [
        campo("FILIAL", "filial"),
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
        campo("FILIAL", "filial"),
        campo("NOTA_BOLETO", "texto", "NOTA/BOLETO"),
        campo("PEDIDO", "texto"),
        campo("MIGO", "texto"),
        campo("NG", "texto"),
        campo("VALOR", "decimal"),
        campo("MES", "mes_nome", "MÊS"),   # coluna text: guarda o nome
        campo(COL_DATA_PAGAMENTO, "data", "DATA PAGAMENTO"),
        campo(COL_BP, "decimal", "BP FORNECEDOR"),
        campo("FIXO", "texto"),
        campo("SETOR", "opcoes", opcoes=OPCOES_SETOR),
    ],
    "reciclaveis": [
        campo("FILIAL", "filial"),
        campo("DATA", "data"),
        # "opcoes" mantém na lista o nome já gravado, mesmo fora da curadoria:
        # editar um registro antigo não reescreve o material sem pedir
        campo("MATERIAL", "opcoes", opcoes=MATERIAIS_RECICLAVEIS),
        campo("PESO", "decimal"),
        campo("VALOR_KG", "decimal", "VALOR/KG"),
        campo("TOTAL", "calculado"),
        campo("PAGAMENTO", "opcoes", opcoes=OPCOES_PAGAMENTO),
    ],
}

# colunas que compõem o rótulo do registro na lista de seleção
RESUMO_REGISTRO = {
    "consumos": ("FILIAL", "MES", "ANO"),
    "licencas": ("FILIAL", "LICENCA", COL_DT_VENCIMENTO),
    "custos": ("FORNECEDOR", "NOTA_BOLETO", "VALOR"),
    "reciclaveis": ("FILIAL", "MATERIAL", "DATA"),
}

AJUSTES_EDICAO = {"reciclaveis": recalcular_total_reciclavel}


def para_int(valor, padrao=0) -> int:
    """Nunca levanta: coluna text pode guardar qualquer coisa.

    ROTA virou text no banco, então um "12A" ou "S/ROTA" chegaria aqui e
    um int() cru derrubava a tela inteira por causa de uma linha.
    """
    if isinstance(valor, float) and valor != valor:   # NaN
        return padrao
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return padrao


def para_float(valor, padrao=0.0) -> float:
    if isinstance(valor, float) and valor != valor:   # NaN
        return padrao
    try:
        convertido = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return padrao
    return padrao if convertido != convertido else convertido


def nome_mes(valor):
    """Devolve o nome do mês a partir de número, texto numérico ou nome.

    MES em SUSTENTABILIDADE_CUSTO é text: as linhas antigas guardam "9" e as
    novas guardam "Setembro". Sem isso, uma linha antiga abriria em Janeiro
    na tela de edição — errado e silencioso.
    """
    if valor in (None, ""):
        return None
    texto = str(valor).strip()
    for existente in MESES:
        if existente.lower() == texto.lower():
            return existente
    numero = para_int(texto, 0)
    return MESES[numero - 1] if 1 <= numero <= 12 else None


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
        return st.text_input(label, value=texto_celula(atual), key=chave)
    if tipo == "texto_longo":
        return st.text_area(label, value=texto_celula(atual), key=chave)
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
    if tipo == "mes_nome":
        atual = nome_mes(atual)
        indice = MESES.index(atual) if atual in MESES else date.today().month - 1
        return st.selectbox(label, MESES, index=indice, key=chave)
    if tipo == "filial":
        opcoes = list(opcoes_filial())
        if not opcoes:
            return st.text_input(
                label, value="" if atual is None else str(atual), key=chave
            )
        # filial gravada fora da lista atual entra na lista, para não ser
        # trocada por outra sem ninguém pedir
        if atual not in (None, "") and atual not in opcoes:
            opcoes = [atual] + opcoes
        indice = opcoes.index(atual) if atual in opcoes else 0
        return st.selectbox(label, opcoes, index=indice, key=chave)
    if tipo == "opcoes":
        opcoes = list(spec["opcoes"])
        # valor fora da lista entra na lista: melhor exibir o que está no
        # banco do que trocar por outro sem avisar
        if atual not in (None, "") and atual not in opcoes:
            opcoes = [atual] + opcoes
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
    partes = [
        texto_celula(linha.get(col))[:22]
        for col in RESUMO_REGISTRO.get(tabela_app, ())
        if texto_celula(linha.get(col))
    ]
    return f"#{linha.get('id')} · " + " · ".join(partes) if partes else f"#{linha.get('id')}"


# ------------------------------------------------
# Busca do registro a editar
# ------------------------------------------------
# Com 784 licenças, rolar uma lista única não funciona. Filtra-se primeiro
# por FILIAL e depois pela coluna que identifica o lançamento; as opções do
# segundo filtro saem do que sobrou do primeiro, então escolher a filial já
# encurta a lista. A tabela exibida e a lista de escolha vêm do MESMO
# conjunto filtrado, na mesma ordem — antes elas divergiam quando a tabela
# era reordenada por um clique no cabeçalho.

FILTROS_EDICAO = {
    "consumos": ("FILIAL", "ANO"),
    "licencas": ("FILIAL", "LICENCA"),
    "custos": ("FILIAL", "FORNECEDOR"),
    "reciclaveis": ("FILIAL", "MATERIAL"),
}
TODAS = "(todas)"


def texto_celula(valor) -> str:
    """Valor de célula como texto limpo; NaN e None viram ''."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor != valor:      # NaN
        return ""
    return str(valor).strip()


def limpa_nulos(registro: dict) -> dict:
    """NaN do pandas volta a ser None.

    df.to_dict() devolve NaN onde a coluna é nula, e str(NaN) == 'nan'. Sem
    esta limpeza o campo OBSERVAÇÃO abre com o texto 'nan' e, ao salvar,
    grava a string 'nan' no banco.
    """
    return {
        chave: (None if isinstance(valor, float) and valor != valor else valor)
        for chave, valor in registro.items()
    }


def aplica_filtros(tabela_app: str, df: pd.DataFrame) -> pd.DataFrame:
    """Desenha os filtros e devolve o subconjunto correspondente."""
    colunas = [c for c in FILTROS_EDICAO.get(tabela_app, ("FILIAL",)) if c in df.columns]
    filtrado = df
    caixas = st.columns(len(colunas) + 1)

    for i, coluna in enumerate(colunas):
        valores = sorted({texto_celula(v) for v in filtrado[coluna]} - {""})
        chave = f"flt_{tabela_app}_{coluna}"
        # se o valor guardado saiu da lista (por causa do filtro anterior ou
        # de uma exclusão), volta para "(todas)" em vez de filtrar por algo
        # que não existe mais
        if st.session_state.get(chave) not in [TODAS] + valores:
            st.session_state.pop(chave, None)
        with caixas[i]:
            escolha = st.selectbox(coluna, [TODAS] + valores, key=chave)
        if escolha != TODAS:
            filtrado = filtrado[filtrado[coluna].map(texto_celula) == escolha]

    with caixas[-1]:
        busca = st.text_input(
            "Buscar",
            key=f"busca_{tabela_app}",
            placeholder="parte de qualquer campo",
        )
    alvo = busca.strip().lower()
    if alvo:
        casa = filtrado.apply(
            lambda linha: alvo in " ".join(texto_celula(v).lower() for v in linha),
            axis=1,
        )
        filtrado = filtrado[casa]

    return filtrado


def painel_edicao(tabela_app: str, limite: int = LIMITE_REGISTROS) -> None:
    """Aba de edição: filtra, escolhe um registro, edita ou exclui."""
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

    if "id" not in df.columns:
        st.warning("A consulta não trouxe a coluna id — sem ela não há como editar.")
        st.dataframe(df, hide_index=True)
        return

    df = df.sort_values("id", ascending=False)
    filtrado = aplica_filtros(tabela_app, df)

    if filtrado.empty:
        st.warning("Nenhum registro com esses filtros.")
        st.caption(f"{len(df)} registro(s) carregado(s) no total.")
        return

    st.dataframe(filtrado, hide_index=True, height=240)
    if len(filtrado) == len(df):
        st.caption(f"{len(df)} registro(s) carregado(s).")
    else:
        st.caption(f"{len(filtrado)} de {len(df)} registro(s) — filtro aplicado.")

    registros = [limpa_nulos(r) for r in filtrado.to_dict("records")]
    rotulos = {rotulo_registro(tabela_app, r): r for r in registros}

    st.divider()
    escolhido = st.selectbox(
        "Registro",
        list(rotulos),
        key=f"sel_{tabela_app}_{versao}",
        help="A lista segue os filtros acima e a mesma ordem da tabela",
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
            type="primary",
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
# A tela tem navegação própria numa barra à esquerda (st.sidebar), uma
# página por assunto. Cada página abre com o relatório: filtros de
# segmentação, a tabela e o botão de extração em XLSX.
#
# A página ativa é marcada com type="primary" — o mesmo verde cheio dos
# botões de gravar. É o único jeito de destacar um botão específico sem
# depender da classe st-key-*, que só existe em versões recentes.

PAGINAS_INDICADOR = {
    "consumos": "Consumos e Serviços",
    "licencas": "Licenças",
    "custos": "Custos e Orçamentos",
    "reciclaveis": "Recicláveis",
}

# Colunas oferecidas como filtro em cada página, na ordem em que aparecem.
# "multi" = multiselect com os valores existentes; "mes" = multiselect que
# mostra nome do mês mas filtra pelo valor gravado (int ou texto).
FILTROS_RELATORIO = {
    "consumos": [("FILIAL", "multi"), ("ANO", "multi"), ("MES", "mes")],
    "licencas": [("FILIAL", "multi"), ("CATEGORIA", "multi"), ("STATUS", "multi")],
    "custos": [
        ("FILIAL", "multi"),
        ("FORNECEDOR", "multi"),
        ("SETOR", "multi"),
        ("MES", "mes"),
    ],
    "reciclaveis": [("FILIAL", "multi"), ("MATERIAL", "multi"), ("PAGAMENTO", "multi")],
}

# Coluna de data para o filtro de período, quando a tabela tem uma
PERIODO_RELATORIO = {"reciclaveis": "DATA"}

# Ordem de leitura do relatório: estas colunas vêm primeiro, o resto entra
# depois na ordem em que o Supabase devolveu. Sem isso, ANO e MES ficavam no
# fim da tabela de consumos (é a ordem em que foram criadas), fora da tela.
COLUNAS_PRIMEIRO = {
    "consumos": ("FILIAL", "ANO", "MES"),
    "licencas": (
        "FILIAL",
        "LICENCA",
        "CATEGORIA",
        "STATUS",
        COL_DT_VENCIMENTO,
        COL_DIAS,
        "CNPJ",
        "ROTA",
    ),
    "custos": ("FILIAL", "FORNECEDOR", "SETOR", "MES", "VALOR", "NOTA_BOLETO"),
    "reciclaveis": (
        "FILIAL",
        "DATA",
        "MATERIAL",
        "PESO",
        "VALOR_KG",
        "TOTAL",
        "PAGAMENTO",
    ),
}

# auditoria é útil, mas no fim: não é o assunto do relatório
COLUNAS_FIM = ("DATA_CRIACAO", "USUARIO")

# "id" é chave técnica do banco, não informação de relatório
COLUNAS_FORA = ("id",)


def colunas_relatorio(pagina: str, df: pd.DataFrame) -> pd.DataFrame:
    """Reordena para leitura humana e descarta a chave técnica."""
    disponiveis = [c for c in df.columns if c not in COLUNAS_FORA]
    primeiro = [c for c in COLUNAS_PRIMEIRO.get(pagina, ()) if c in disponiveis]
    fim = [c for c in COLUNAS_FIM if c in disponiveis]
    meio = [c for c in disponiveis if c not in primeiro and c not in fim]
    return df[primeiro + meio + fim]


# Somas exibidas acima da tabela: (coluna, rótulo, formato)
RESUMOS_RELATORIO = {
    "consumos": [
        (COL_SOLIDOS, "Sólidos contaminados", "num"),
        ("AGUA", "Água", "num"),
        ("ENERGIA", "Energia", "num"),
    ],
    "licencas": [],
    "custos": [("VALOR", "Valor total", "brl")],
    "reciclaveis": [("PESO", "Peso total (kg)", "num"), ("TOTAL", "Receita", "brl")],
}


def fmt_num(valor: float) -> str:
    texto = f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return texto


def para_xlsx(df: pd.DataFrame, aba: str):
    """DataFrame -> bytes de um .xlsx. Devolve (bytes, erro).

    Depende de openpyxl, que é dependência do pandas para Excel e pode não
    estar no requirements.txt. Em vez de estourar na tela, devolve o erro
    para a chamada oferecer CSV.
    """
    try:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
            df.to_excel(escritor, index=False, sheet_name=aba[:31])
        return buffer.getvalue(), None
    except Exception as erro:
        return None, str(erro)


def filtros_relatorio(pagina: str, df: pd.DataFrame) -> pd.DataFrame:
    """Multiselects de segmentação + período. Vazio = não filtra."""
    especificacao = [
        (col, tipo)
        for col, tipo in FILTROS_RELATORIO.get(pagina, [])
        if col in df.columns
    ]
    coluna_data = PERIODO_RELATORIO.get(pagina)
    tem_periodo = coluna_data in df.columns if coluna_data else False

    filtrado = df
    caixas = st.columns(len(especificacao) + (1 if tem_periodo else 0) or 1)

    for i, (coluna, tipo) in enumerate(especificacao):
        if tipo == "mes":
            # a coluna guarda 9 ou "Setembro" conforme a tabela; o rótulo é
            # sempre o nome, e o filtro compara pelo valor original
            mapa = {}
            for bruto in filtrado[coluna]:
                texto = texto_celula(bruto)
                if texto:
                    mapa.setdefault(nome_mes(texto) or texto, set()).add(texto)

            rotulos = sorted(mapa, key=lambda n: MESES.index(n) if n in MESES else 99)
            with caixas[i]:
                escolhidos = st.multiselect(coluna, rotulos, key=f"rel_{pagina}_{coluna}")
            if escolhidos:
                aceitos = {v for r in escolhidos for v in mapa[r]}
                filtrado = filtrado[filtrado[coluna].map(texto_celula).isin(aceitos)]
            continue

        valores = sorted({texto_celula(v) for v in filtrado[coluna]} - {""})
        with caixas[i]:
            escolhidos = st.multiselect(coluna, valores, key=f"rel_{pagina}_{coluna}")
        if escolhidos:
            filtrado = filtrado[filtrado[coluna].map(texto_celula).isin(escolhidos)]

    if tem_periodo:
        datas = [d for d in (para_data(v) for v in filtrado[coluna_data]) if d]
        with caixas[-1]:
            if datas:
                periodo = st.date_input(
                    f"{coluna_data} (período)",
                    value=(min(datas), max(datas)),
                    format="DD/MM/YYYY",
                    key=f"rel_{pagina}_periodo",
                )
            else:
                periodo = None
                st.caption(f"Sem {coluna_data} para filtrar")
        if isinstance(periodo, (tuple, list)) and len(periodo) == 2:
            inicio, fim = periodo
            dentro = filtrado[coluna_data].map(
                lambda v: (para_data(v) is not None) and (inicio <= para_data(v) <= fim)
            )
            filtrado = filtrado[dentro]

    return filtrado


def barra_paginas() -> str:
    """Navegação da tela de indicadores, na lateral esquerda."""
    st.session_state.setdefault("ind_pagina", "consumos")

    with st.sidebar:
        st.markdown('<p class="dv-sidebar-titulo">Páginas</p>', unsafe_allow_html=True)
        for chave, nome in PAGINAS_INDICADOR.items():
            ativa = st.session_state["ind_pagina"] == chave
            st.button(
                nome,
                key=f"ind_pg_{chave}",
                use_container_width=True,
                type="primary" if ativa else "secondary",
                on_click=lambda c=chave: st.session_state.__setitem__("ind_pagina", c),
            )
        st.divider()
        st.caption(
            "Acesso: todas as filiais"
            if PERFIL["admin"]
            else "Filiais: " + ", ".join(PERFIL["filiais"])
        )

    return st.session_state["ind_pagina"]


# ------------------------------------------------
# Gráficos (Plotly)
# ------------------------------------------------
# O import é tolerante: se plotly não estiver no requirements.txt do repo, o
# app continua de pé e a aba de análise avisa o que falta, em vez de morrer
# no import e derrubar até a tela de login.
try:
    import plotly.express as px

    TEM_PLOTLY = True
except ImportError:  # pragma: no cover
    px = None
    TEM_PLOTLY = False

# verde e laranja Della Volpe na frente; o resto são variações para séries
CORES_DV = [
    "#1F7A3D", "#E4610A", "#3F9D5A", "#F0902B",
    "#14532D", "#B84E08", "#7FBF91", "#F6B87A",
]


def estiliza(fig, altura: int = 330):
    """Paleta, fonte e — importante — número em português.

    separators=",." faz o Plotly escrever 1.234,56 em eixos, rótulos e
    hover. Sem isso todo valor sai no padrão americano.
    """
    fig.update_layout(
        colorway=CORES_DV,
        separators=",.",
        height=altura,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Poppins, Segoe UI, sans-serif", size=12, color="#3C4B42"),
        hoverlabel=dict(bgcolor="#14532D", font_size=12, font_color="#FFFFFF"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(gridcolor="#E3EAE4", zerolinecolor="#DCE5DD", title=None),
    )
    return fig


def aviso_sem_plotly() -> None:
    st.warning(
        "Gráficos indisponíveis: falta o pacote **plotly** no "
        "requirements.txt. Os relatórios e a extração continuam funcionando."
    )


# Serviços da tela de Consumos. Todas as colunas são VALOR PAGO em reais —
# não são volumes. Por isso somar entre elas faz sentido e a matriz tem
# coluna de total.
SERVICOS_CONSUMO = [
    (COL_SOLIDOS, "Sólidos contaminados"),
    (COL_OLEO, "Óleo lubrificante"),
    ("AGUA", "Água"),
    ("ENERGIA", "Energia"),
    ("COMUM", "Comum"),
    ("MADEIRA", "Madeira"),
    ("RECICLAVEIS", "Recicláveis"),
    ("CO2", "CO²"),
]


# ------------------------------------------------
# Cartões de indicador (HTML, para poder pintar)
# ------------------------------------------------
# st.metric não permite cor por cartão — todos ficariam iguais. Em HTML dá
# controle de fundo, faixa lateral e seta, que é o que diferencia "receita"
# de "pendente" num relance.
# rótulo do primeiro cartão (a contagem de linhas) por página
ROTULO_CONTAGEM = {
    "consumos": "Lançamentos",
    "licencas": "Total de licenças",
    "reciclaveis": "Lançamentos",
    "custos": "Lançamentos",
}

CARTOES_PAGINA = {
    # a coluna pode ser uma lista: soma horizontal dos serviços
    "consumos": [
        ("Valor total", [c for c, _ in SERVICOS_CONSUMO], "brl", "verde", None),
    ],
    # formato "cont" conta linhas em vez de somar uma coluna
    "licencas": [
        ("Vencidas", None, "cont", "vermelho", ("STATUS", "VENCIDO")),
        ("Renovar", None, "cont", "laranja", ("STATUS", "RENOVAR")),
        ("No prazo", None, "cont", "verde", ("STATUS", "NO PRAZO")),
    ],
    "custos": [("Valor total", "VALOR", "brl", "verde", None)],
    "reciclaveis": [
        ("Receita total", "TOTAL", "brl", "verde", None),
        # pedido: soma de TOTAL apenas onde o pagamento não entrou
        ("Pagamento pendente", "TOTAL", "brl", "laranja",
         ("PAGAMENTO", "Aguardando Pagamento")),
        ("Peso total", "PESO", "kg", "neutro", None),
    ],
}


def formata_valor(valor: float, formato: str) -> str:
    if formato == "brl":
        return fmt_brl(valor)
    if formato == "kg":
        return f"{fmt_num(valor)} kg"
    return fmt_num(valor)


def cartao_kpi(rotulo: str, valor: str, cor: str = "neutro", nota: str = "") -> str:
    return (
        f'<div class="dv-kpi {cor}">'
        f'<span class="dv-kpi-rotulo">{rotulo}</span>'
        f"<strong>{valor}</strong>"
        f'<span class="dv-kpi-nota">{nota}</span>'
        "</div>"
    )


def linha_cartoes(cartoes: list) -> None:
    """cartoes = [(rotulo, valor_formatado, cor, nota), ...]"""
    if not cartoes:
        return
    caixas = st.columns(len(cartoes))
    for caixa, (rotulo, valor, cor, nota) in zip(caixas, cartoes):
        with caixa:
            st.markdown(cartao_kpi(rotulo, valor, cor, nota), unsafe_allow_html=True)


def cartoes_da_pagina(pagina: str, df: pd.DataFrame) -> None:
    cartoes = [
        (ROTULO_CONTAGEM.get(pagina, "Registros"), f"{len(df)}", "neutro",
         "todos os status" if pagina == "licencas" else "no filtro atual")
    ]
    for rotulo, coluna, formato, cor, condicao in CARTOES_PAGINA.get(pagina, []):
        # coluna pode ser uma lista (soma de vários campos)
        colunas = coluna if isinstance(coluna, (list, tuple)) else [coluna]
        colunas = [c for c in colunas if c in df.columns]
        if formato != "cont" and not colunas:
            continue

        recorte = df
        nota = ""
        if condicao is not None:
            col_cond, valor_cond = condicao
            if col_cond not in df.columns:
                continue
            # comparação sem caixa: as linhas antigas podem ter "Vencido"
            recorte = df[
                df[col_cond].map(lambda v: texto_celula(v).upper()) == valor_cond.upper()
            ]

        if formato == "cont":
            proporcao = f"{len(recorte) / len(df):.0%}" if len(df) else "0%"
            cartoes.append((rotulo, f"{len(recorte)}", cor, f"{proporcao} do total"))
            continue

        if condicao is not None:
            nota = f"{len(recorte)} de {len(df)} lançamentos"
        soma = sum(
            pd.to_numeric(recorte[c], errors="coerce").fillna(0).sum() for c in colunas
        )
        if len(colunas) > 1 and not nota:
            nota = f"{len(colunas)} serviços somados"
        cartoes.append((rotulo, formata_valor(soma, formato), cor, nota))
    linha_cartoes(cartoes)


# ------------------------------------------------
# Competência: a coluna que permite série temporal
# ------------------------------------------------
def com_competencia(pagina: str, df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta ANO_N, MES_N e COMPETENCIA (1º dia do mês).

    Consumos não tem coluna de data — tem ANO e MES separados. Custos guarda
    o mês como TEXTO ("Setembro"), que ordenado dá ordem alfabética. Aqui as
    três tabelas passam a ter a mesma referência temporal.
    """
    saida = df.copy()

    if pagina == "consumos":
        saida["ANO_N"] = saida["ANO"].map(lambda v: para_int(v, 0))
        saida["MES_N"] = saida["MES"].map(lambda v: para_int(v, 0))
    elif pagina == "reciclaveis":
        datas = saida["DATA"].map(para_data)
        saida["ANO_N"] = datas.map(lambda d: d.year if d else 0)
        saida["MES_N"] = datas.map(lambda d: d.month if d else 0)
    elif pagina == "custos":
        # Régua do tempo: DATA_PAGAMENTO (regime de caixa). Ela define ano E
        # mês. A coluna MES existe em paralelo, em texto e sem ano — usá-la
        # obrigaria a adivinhar o ano em outro lugar. Lançamento sem data de
        # pagamento fica sem competência e sai da série; quem chama expõe
        # isso num cartão em vez de deixar a soma divergir em silêncio.
        datas = saida[COL_DATA_PAGAMENTO].map(para_data)
        saida["ANO_N"] = datas.map(lambda d: d.year if d else 0)
        saida["MES_N"] = datas.map(lambda d: d.month if d else 0)
    else:
        saida["ANO_N"] = 0
        saida["MES_N"] = 0

    saida = saida[(saida["ANO_N"] > 0) & (saida["MES_N"].between(1, 12))]
    saida["COMPETENCIA"] = [
        date(int(a), int(m), 1) for a, m in zip(saida["ANO_N"], saida["MES_N"])
    ]
    saida["MES_NOME"] = saida["MES_N"].map(lambda m: MESES[int(m) - 1])
    return saida


def sinal_valor(diferenca: float) -> str:
    return ("+" if diferenca >= 0 else "−") + fmt_brl(abs(diferenca))


def resumo_anual(base: pd.DataFrame, coluna: str):
    """Totais do ano corrente e do ano anterior nos MESMOS meses fechados.

    Comparar 2026 até agosto com 2025 inteiro mostraria uma queda que não
    existe — são 8 meses contra 12. E o mês corrente, ainda aberto, também
    fica fora: 5 dias de setembro contra setembro inteiro do ano passado
    inventaria economia.

    Uma função só para que cartão, comparativo e gráfico não divirjam.
    """
    if base.empty:
        return None

    valores = pd.to_numeric(base[coluna], errors="coerce").fillna(0)
    trabalho = base.assign(_v=valores)

    ano_atual = int(trabalho["ANO_N"].max())
    meses = sorted({int(m) for m in trabalho[trabalho["ANO_N"] == ano_atual]["MES_N"]})
    if not meses:
        return None

    hoje = date.today()
    aberto = False
    if ano_atual == hoje.year:
        fechados = [m for m in meses if m < hoje.month]
        if fechados:
            meses = fechados
        else:
            aberto = True

    do_ano = trabalho[(trabalho["ANO_N"] == ano_atual) & (trabalho["MES_N"].isin(meses))]
    anterior = trabalho[
        (trabalho["ANO_N"] == ano_atual - 1) & (trabalho["MES_N"].isin(meses))
    ]
    total_anterior = anterior["_v"].sum()

    faixa = (
        f"{MESES[meses[0] - 1][:3]}–{MESES[meses[-1] - 1][:3]}"
        if len(meses) > 1
        else MESES[meses[0] - 1][:3]
    )

    return {
        "ano": ano_atual,
        "meses": meses,
        "faixa": faixa,
        "aberto": aberto,
        "total": float(do_ano["_v"].sum()),
        "total_anterior": float(total_anterior),
        "tem_base": (not anterior.empty) and total_anterior != 0,
    }


def comparativo_anual(base: pd.DataFrame, coluna: str, subir_e_bom: bool = True):
    """Cartão de variação ano a ano. Devolve (cartão, faixa) ou (None, None).

    subir_e_bom=False inverte a cor: gasto subindo é resultado ruim.
    """
    resumo = resumo_anual(base, coluna)
    if resumo is None:
        return None, None

    ano_atual = resumo["ano"]
    faixa = resumo["faixa"]
    aberto = resumo["aberto"]
    total_atual = resumo["total"]
    total_anterior = resumo["total_anterior"]

    if not resumo["tem_base"]:
        return (
            (
                f"{ano_atual} vs {ano_atual - 1}",
                "sem base",
                "neutro",
                f"nada lançado em {faixa}/{ano_atual - 1}",
            ),
            faixa,
        )

    diferenca = total_atual - total_anterior
    variacao = diferenca / total_anterior
    subiu = diferenca >= 0
    cor = ("verde" if subiu else "laranja") if subir_e_bom else ("laranja" if subiu else "verde")
    seta = "▲" if subiu else "▼"
    percentual = f"{abs(variacao):.1%}".replace(".", ",")

    return (
        (
            f"{ano_atual} vs {ano_atual - 1}",
            f"{seta} {percentual}",
            cor,
            f"{sinal_valor(diferenca)} · {faixa}: "
            f"{fmt_brl(total_atual)} contra {fmt_brl(total_anterior)}"
            + (" · mês corrente ainda aberto" if aberto else ""),
        ),
        faixa,
    )


# ------------------------------------------------
# Análise: Recicláveis
# ------------------------------------------------
def analise_reciclaveis(df: pd.DataFrame) -> None:
    if not TEM_PLOTLY:
        aviso_sem_plotly()
        return

    base = com_competencia("reciclaveis", df)
    if base.empty:
        st.info("Sem registros com data válida para montar os gráficos.")
        return

    base["TOTAL_N"] = pd.to_numeric(base["TOTAL"], errors="coerce").fillna(0)

    # receita subindo é resultado bom — o oposto de consumo
    cartao, faixa = comparativo_anual(base, "TOTAL_N", subir_e_bom=True)
    if cartao is not None:
        linha_cartoes([cartao])
        st.caption(
            "A comparação usa os mesmos meses nos dois anos "
            f"({faixa}), senão um ano incompleto pareceria queda."
        )

    esq, dir_ = st.columns([1, 1])

    with esq:
        st.markdown("**Receita por ano**")
        anual = base.groupby("ANO_N", as_index=False)["TOTAL_N"].sum()
        fig = px.bar(anual, x="ANO_N", y="TOTAL_N", text="TOTAL_N")
        fig.update_traces(
            texttemplate="R$ %{text:,.0f}",
            textposition="outside",
            # sem cliponaxis o rótulo da maior barra é cortado pela borda
            cliponaxis=False,
            hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
            marker_color=CORES_DV[0],
        )
        fig.update_xaxes(type="category")
        fig.update_yaxes(range=[0, float(anual["TOTAL_N"].max()) * 1.18])
        st.plotly_chart(estiliza(fig), use_container_width=True)

    with dir_:
        st.markdown("**Receita por material** — do maior para o menor")
        por_material = (
            base.groupby("MATERIAL", as_index=False)["TOTAL_N"]
            .sum()
            .sort_values("TOTAL_N", ascending=True)  # asc: o maior fica no topo
        )
        fig = px.bar(por_material, x="TOTAL_N", y="MATERIAL", orientation="h",
                     text="TOTAL_N")
        fig.update_traces(
            texttemplate="R$ %{text:,.0f}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>",
            marker_color=CORES_DV[0],
        )
        # 22% de folga à direita: era o que faltava para o rótulo do maior
        # material caber dentro da figura
        fig.update_xaxes(range=[0, float(por_material["TOTAL_N"].max()) * 1.22])
        altura = max(330, 26 * len(por_material) + 90)
        st.plotly_chart(estiliza(fig, altura), use_container_width=True)

    st.markdown("**Receita por mês**")
    mensal = base.groupby("COMPETENCIA", as_index=False)["TOTAL_N"].sum()
    mensal["rotulo"] = [
        f"{MESES[d.month - 1][:3]}/{d.year}" for d in mensal["COMPETENCIA"]
    ]
    fig = px.bar(mensal, x="rotulo", y="TOTAL_N")
    fig.update_traces(
        hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
        marker_color=CORES_DV[1],
    )
    fig.update_xaxes(type="category", tickangle=-60)
    st.plotly_chart(estiliza(fig, 360), use_container_width=True)
    st.caption(
        f"{len(mensal)} mês(es) com lançamento, de "
        f"{mensal['rotulo'].iloc[0]} a {mensal['rotulo'].iloc[-1]}."
    )


# ------------------------------------------------
# Análise: Consumos e Serviços
# ------------------------------------------------
def analise_consumos(df: pd.DataFrame) -> None:
    base = com_competencia("consumos", df)
    if base.empty:
        st.info("Sem registros com ANO e MÊS válidos para montar a análise.")
        return

    colunas = [(c, r) for c, r in SERVICOS_CONSUMO if c in base.columns]
    for coluna, _ in colunas:
        base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0)

    # ---------- filtro de serviço ----------
    rotulos = {r: c for c, r in colunas}
    escolhidos = st.multiselect(
        "Serviços",
        list(rotulos),
        key="ind_consumo_servicos",
        help="Vazio = todos os serviços somados",
    )
    selecionados = [rotulos[r] for r in escolhidos] or [c for c, _ in colunas]
    base["VALOR"] = base[selecionados].sum(axis=1)
    titulo_selecao = ", ".join(escolhidos) if escolhidos else "todos os serviços"

    # ---------- cartões de gasto ----------
    resumo = resumo_anual(base, "VALOR")
    cartoes = []
    if resumo is not None:
        cartoes.append(
            (
                f"Gasto {resumo['faixa']}/{resumo['ano']}",
                fmt_brl(resumo["total"]),
                "neutro",
                titulo_selecao,
            )
        )
        if resumo["tem_base"]:
            cartoes.append(
                (
                    f"Mesmo período {resumo['ano'] - 1}",
                    fmt_brl(resumo["total_anterior"]),
                    "neutro",
                    f"{resumo['faixa']}/{resumo['ano'] - 1}",
                )
            )
        # gasto subindo é resultado ruim: a seta inverte
        cartao_ano, _ = comparativo_anual(base, "VALOR", subir_e_bom=False)
        if cartao_ano is not None:
            cartoes.append(cartao_ano)

    # ---------- último mês fechado vs. o anterior ----------
    serie = base.groupby(["ANO_N", "MES_N"], as_index=False)["VALOR"].sum()

    def valor_em(ano: int, mes: int):
        linha = serie[(serie["ANO_N"] == ano) & (serie["MES_N"] == mes)]
        return float(linha["VALOR"].iloc[0]) if not linha.empty else None

    if resumo is not None and resumo["meses"]:
        ano_ref, mes_ref = resumo["ano"], resumo["meses"][-1]
        atual = valor_em(ano_ref, mes_ref) or 0.0
        ano_ant, mes_ant = (ano_ref, mes_ref - 1) if mes_ref > 1 else (ano_ref - 1, 12)
        anterior = valor_em(ano_ant, mes_ant)

        if anterior:
            delta = (atual - anterior) / anterior
            subiu = delta >= 0
            cartoes.append(
                (
                    f"{MESES[mes_ref - 1]}/{ano_ref} vs. mês anterior",
                    f"{'▲' if subiu else '▼'} {abs(delta):.1%}".replace(".", ","),
                    "laranja" if subiu else "verde",
                    f"{fmt_brl(atual)} · {MESES[mes_ant - 1]}/{ano_ant}: {fmt_brl(anterior)}",
                )
            )
        else:
            cartoes.append(
                (
                    f"{MESES[mes_ref - 1]}/{ano_ref}",
                    fmt_brl(atual),
                    "neutro",
                    "sem mês anterior para comparar",
                )
            )

    linha_cartoes(cartoes)
    if resumo is not None and resumo["tem_base"]:
        st.caption(
            "A comparação anual usa os mesmos meses nos dois anos "
            f"({resumo['faixa']}), e só meses fechados — o mês corrente fica "
            "de fora para não parecer economia."
        )

    # ---------- matriz ano x serviço ----------
    st.divider()
    st.markdown("**Valor pago por ano e serviço (R$)**")
    matriz = base.groupby("ANO_N")[[c for c, _ in colunas]].sum()
    matriz.index.name = "ANO"
    matriz["TOTAL"] = matriz.sum(axis=1)
    exibir = matriz.rename(columns=dict(colunas)).sort_index(ascending=False)
    st.dataframe(exibir.map(fmt_brl), use_container_width=True)
    st.caption(
        "Todos os campos são valores pagos, então a coluna TOTAL soma a "
        "linha. A matriz ignora o filtro de serviço acima, de propósito: "
        "ela é a visão completa do ano."
    )

    if not TEM_PLOTLY:
        aviso_sem_plotly()
        return

    # ---------- uma linha por ano ----------
    # este é o gráfico que responde às duas comparações de uma vez: a
    # inclinação da linha é o mês contra o anterior, e a distância entre as
    # linhas é o mesmo mês contra o ano passado
    st.divider()
    st.markdown(f"**Gasto mensal — {titulo_selecao}**")
    grafico = serie.copy()
    grafico["MES_NOME"] = grafico["MES_N"].map(lambda m: MESES[int(m) - 1])
    grafico["ANO"] = grafico["ANO_N"].astype(str)

    fig = px.line(
        grafico.sort_values(["ANO_N", "MES_N"]),
        x="MES_NOME", y="VALOR", color="ANO", markers=True,
        category_orders={"MES_NOME": MESES},
    )
    fig.update_traces(
        hovertemplate="%{x}<br>R$ %{y:,.2f}<extra>%{fullData.name}</extra>"
    )
    st.plotly_chart(estiliza(fig, 380), use_container_width=True)
    st.caption(
        "Cada linha é um ano. A inclinação mostra o mês contra o anterior; "
        "a distância entre as linhas, o mesmo mês contra o ano passado."
    )

# ------------------------------------------------
# Análise: Licenças
# ------------------------------------------------
# Cor por significado, não pela ordem da paleta: um "VENCIDO" pintado de
# verde porque saiu primeiro no groupby seria pior que não ter gráfico.
CORES_STATUS = {
    "NO PRAZO": "#1F7A3D",
    "RENOVAR": "#E4610A",
    "VENCIDO": "#B3261E",
    "NÃO SE APLICA": "#9AA8A0",
    "(sem status)": "#C9DACE",
}
SEM_STATUS = "(sem status)"


def analise_licencas(df: pd.DataFrame) -> None:
    if not TEM_PLOTLY:
        aviso_sem_plotly()
        return
    if "FILIAL" not in df.columns or "STATUS" not in df.columns:
        st.info("Faltam as colunas FILIAL e STATUS para montar o gráfico.")
        return

    base = df.copy()
    # status vazio não pode sumir no groupby: senão a soma das barras deixa
    # de fechar com o cartão de total
    base["STATUS_N"] = base["STATUS"].map(
        lambda v: texto_celula(v).upper() or SEM_STATUS
    )
    base["FILIAL_N"] = base["FILIAL"].map(lambda v: texto_celula(v) or "(sem filial)")

    contagem = (
        base.groupby(["FILIAL_N", "STATUS_N"]).size().reset_index(name="QTD")
    )
    totais = contagem.groupby("FILIAL_N", as_index=False)["QTD"].sum()
    ordem = totais.sort_values("QTD", ascending=True)["FILIAL_N"].tolist()

    st.markdown("**Licenças por filial e status**")
    fig = px.bar(
        contagem,
        x="QTD",
        y="FILIAL_N",
        color="STATUS_N",
        orientation="h",
        text="QTD",
        category_orders={"FILIAL_N": ordem, "STATUS_N": list(CORES_STATUS)},
        color_discrete_map=CORES_STATUS,
    )
    fig.update_traces(
        textposition="inside",
        insidetextanchor="middle",
        textfont_size=11,
        hovertemplate="%{y}<br>%{fullData.name}: %{x}<extra></extra>",
    )
    fig.update_layout(barmode="stack")

    # o total de cada barra, à direita — o rótulo interno é por status
    maior = int(totais["QTD"].max())
    for _, linha in totais.iterrows():
        fig.add_annotation(
            x=int(linha["QTD"]),
            y=linha["FILIAL_N"],
            text=f"<b>{int(linha['QTD'])}</b>",
            showarrow=False,
            xanchor="left",
            xshift=6,
            font=dict(size=11, color="#3C4B42"),
        )
    fig.update_xaxes(range=[0, maior * 1.12])

    altura = max(340, 24 * len(ordem) + 110)
    st.plotly_chart(estiliza(fig, altura), use_container_width=True)
    st.caption(
        f"{len(base)} licença(s) em {len(ordem)} filial(is). O número dentro "
        "de cada faixa é a quantidade daquele status; o número à direita é o "
        "total da filial."
    )


# ------------------------------------------------
# Análise: Custos e Orçamentos
# ------------------------------------------------
# A régua do tempo aqui é a DATA_PAGAMENTO — regime de caixa: o gasto conta
# no mês em que o dinheiro saiu. Consequência inevitável: lançamento sem
# data de pagamento não tem competência e fica fora da série. Em vez de
# desaparecer em silêncio, ele aparece num cartão próprio, para a soma dos
# gráficos poder ser conferida contra o cartão de valor total.
def analise_custos(df: pd.DataFrame) -> None:
    if "VALOR" not in df.columns:
        st.info("Falta a coluna VALOR para montar a análise.")
        return

    # o que não entra na série temporal, e quanto isso representa
    if COL_DATA_PAGAMENTO in df.columns:
        sem_data = df[df[COL_DATA_PAGAMENTO].map(lambda v: para_data(v) is None)]
    else:
        sem_data = df.iloc[0:0]
    valor_sem_data = pd.to_numeric(sem_data["VALOR"], errors="coerce").fillna(0).sum()

    base = com_competencia("custos", df)
    if base.empty:
        st.warning(
            "Nenhum lançamento com DATA_PAGAMENTO legível — sem isso não há "
            "como montar a série por mês."
        )
        if len(sem_data):
            st.caption(
                f"{len(sem_data)} lançamento(s) sem data de pagamento, "
                f"somando {fmt_brl(valor_sem_data)}."
            )
        return

    base["VALOR_N"] = pd.to_numeric(base["VALOR"], errors="coerce").fillna(0)

    # ---------- cartões ----------
    resumo = resumo_anual(base, "VALOR_N")
    cartoes = []
    if resumo is not None:
        cartoes.append(
            (
                f"Pago {resumo['faixa']}/{resumo['ano']}",
                fmt_brl(resumo["total"]),
                "neutro",
                "por data de pagamento",
            )
        )
        if resumo["tem_base"]:
            cartoes.append(
                (
                    f"Mesmo período {resumo['ano'] - 1}",
                    fmt_brl(resumo["total_anterior"]),
                    "neutro",
                    f"{resumo['faixa']}/{resumo['ano'] - 1}",
                )
            )
        # gasto subindo é resultado ruim: seta invertida
        cartao_ano, _ = comparativo_anual(base, "VALOR_N", subir_e_bom=False)
        if cartao_ano is not None:
            cartoes.append(cartao_ano)

    serie = base.groupby(["ANO_N", "MES_N"], as_index=False)["VALOR_N"].sum()

    def valor_em(ano: int, mes: int):
        linha = serie[(serie["ANO_N"] == ano) & (serie["MES_N"] == mes)]
        return float(linha["VALOR_N"].iloc[0]) if not linha.empty else None

    if resumo is not None and resumo["meses"]:
        ano_ref, mes_ref = resumo["ano"], resumo["meses"][-1]
        atual = valor_em(ano_ref, mes_ref) or 0.0
        ano_ant, mes_ant = (ano_ref, mes_ref - 1) if mes_ref > 1 else (ano_ref - 1, 12)
        anterior = valor_em(ano_ant, mes_ant)
        if anterior:
            delta = (atual - anterior) / anterior
            subiu = delta >= 0
            cartoes.append(
                (
                    f"{MESES[mes_ref - 1]}/{ano_ref} vs. mês anterior",
                    f"{'▲' if subiu else '▼'} {abs(delta):.1%}".replace(".", ","),
                    "laranja" if subiu else "verde",
                    f"{fmt_brl(atual)} · {MESES[mes_ant - 1]}/{ano_ant}: {fmt_brl(anterior)}",
                )
            )
        else:
            cartoes.append(
                (
                    f"{MESES[mes_ref - 1]}/{ano_ref}",
                    fmt_brl(atual),
                    "neutro",
                    "sem mês anterior para comparar",
                )
            )

    if len(sem_data):
        cartoes.append(
            (
                "Sem data de pagamento",
                fmt_brl(valor_sem_data),
                "laranja",
                f"{len(sem_data)} lançamento(s) fora da série",
            )
        )

    linha_cartoes(cartoes)
    if resumo is not None and resumo["tem_base"]:
        st.caption(
            "A comparação anual usa os mesmos meses nos dois anos "
            f"({resumo['faixa']}) e só meses fechados — o mês corrente fica "
            "de fora para não parecer economia."
        )

    if not TEM_PLOTLY:
        aviso_sem_plotly()
        return

    # ---------- por ano ----------
    st.divider()
    esq, dir_ = st.columns([1, 2])

    with esq:
        st.markdown("**Pago por ano**")
        anual = base.groupby("ANO_N", as_index=False)["VALOR_N"].sum()
        fig = px.bar(anual, x="ANO_N", y="VALOR_N", text="VALOR_N")
        fig.update_traces(
            texttemplate="R$ %{text:,.0f}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
            marker_color=CORES_DV[0],
        )
        fig.update_xaxes(type="category")
        fig.update_yaxes(range=[0, float(anual["VALOR_N"].max()) * 1.18])
        st.plotly_chart(estiliza(fig), use_container_width=True)

    # ---------- mês a mês, uma linha por ano ----------
    with dir_:
        st.markdown("**Pago por mês** — uma linha por ano")
        grafico = serie.copy()
        grafico["MES_NOME"] = grafico["MES_N"].map(lambda m: MESES[int(m) - 1])
        grafico["ANO"] = grafico["ANO_N"].astype(str)
        fig = px.line(
            grafico.sort_values(["ANO_N", "MES_N"]),
            x="MES_NOME", y="VALOR_N", color="ANO", markers=True,
            category_orders={"MES_NOME": MESES},
        )
        fig.update_traces(
            hovertemplate="%{x}<br>R$ %{y:,.2f}<extra>%{fullData.name}</extra>"
        )
        st.plotly_chart(estiliza(fig), use_container_width=True)

    st.caption(
        f"{len(base)} lançamento(s) com data de pagamento"
        + (
            f" · {len(sem_data)} sem data ({fmt_brl(valor_sem_data)}) não entram "
            "nos gráficos"
            if len(sem_data)
            else ""
        )
        + ". A inclinação da linha é o mês contra o anterior; a distância "
        "entre as linhas, o mesmo mês contra o ano passado."
    )


ANALISES = {
    "reciclaveis": analise_reciclaveis,
    "consumos": analise_consumos,
    "licencas": analise_licencas,
    "custos": analise_custos,
}


def pagina_relatorio(pagina: str) -> None:
    nome = PAGINAS_INDICADOR[pagina]
    st.markdown(f"### {nome}")

    try:
        df = listar_registros(pagina)
    except Exception as erro:
        st.error(f"Não foi possível ler {TABELAS_DB[pagina]}: {erro}")
        return

    if df.empty:
        st.info("Nenhum registro para relatar.")
        return

    filtrado = filtros_relatorio(pagina, df)

    if filtrado.empty:
        st.warning("Nenhum registro com esses filtros.")
        st.caption(f"{len(df)} registro(s) na base.")
        return

    # o filtro de período usa a coluna de data crua, então a reordenação
    # (e o descarte do id) vem só agora
    filtrado = colunas_relatorio(pagina, filtrado)

    cartoes_da_pagina(pagina, filtrado)

    analise = ANALISES.get(pagina)
    if analise is None:
        bloco_relatorio(pagina, filtrado, df)
        return

    aba_analise, aba_relatorio = st.tabs(["📊 Análise", "📄 Relatório"])
    with aba_analise:
        analise(filtrado)
    with aba_relatorio:
        bloco_relatorio(pagina, filtrado, df)


def bloco_relatorio(pagina: str, filtrado: pd.DataFrame, df: pd.DataFrame) -> None:
    """Tabela + extração. Recebe já filtrado para o arquivo sair igual à tela."""
    nome = PAGINAS_INDICADOR[pagina]   # vira o nome da aba no xlsx
    st.dataframe(filtrado, hide_index=True, height=380)
    if len(filtrado) == len(df):
        st.caption(f"{len(df)} registro(s).")
    else:
        st.caption(f"{len(filtrado)} de {len(df)} registro(s) — filtro aplicado.")

    # ---- extração ----
    marca = datetime.now().strftime("%Y%m%d_%H%M")
    conteudo, erro = para_xlsx(filtrado, nome)
    esq, dir_ = st.columns([1, 3])
    if conteudo is not None:
        with esq:
            st.download_button(
                "⬇️ Extrair XLSX",
                data=conteudo,
                file_name=f"{TABELAS_DB[pagina]}_{marca}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        with dir_:
            st.caption("O arquivo sai exatamente com as linhas filtradas acima.")
    else:
        # sem openpyxl não há xlsx; CSV resolve sem depender de biblioteca
        with esq:
            st.download_button(
                "⬇️ Extrair CSV",
                data=filtrado.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"{TABELAS_DB[pagina]}_{marca}.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True,
            )
        with dir_:
            st.warning(
                "XLSX indisponível: falta o pacote **openpyxl** no "
                f"requirements.txt. Enquanto isso, o CSV sai com separador "
                f"`;` e acentuação correta no Excel. ({erro})"
            )


def tela_indicador() -> None:
    cabecalho_tela("indicador")
    pagina = barra_paginas()
    pagina_relatorio(pagina)


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

# A navegação é por st.button (ir_para), nunca por link: um <a href> faz o
# navegador recarregar a página, o Streamlit abre uma sessão nova, o token
# do Azure em st.session_state se perde e o login é pedido outra vez.
ROTAS.get(st.session_state["tela"], tela_menu)()
