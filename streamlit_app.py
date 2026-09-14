import streamlit as st
import pandas as pd
import supabase
import sys
import subprocess
from pathlib import Path, PureWindowsPath
from datetime import datetime, timedelta, date
import os
import tempfile
import unicodedata
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
# jobTitle vem na resposta padrão do /me — não precisa de scope extra nem
# de coluna no cadastro. Fica vazio quando o RH não preencheu no AD.
user_cargo = user_info.get("jobTitle") or ""
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
st.session_state["user_cargo"] = user_cargo
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
    "ambiental": "SUSTENTABILIDADE_LICENCAS",
    "custos": "SUSTENTABILIDADE_CUSTO",
    "reciclaveis": "SUSTENTABILIDADE_RECICLAVEIS",
    "pgrs": "SUSTENTABILIDADE_PRGS",
}

# Controle de Licenças e Controles Ambientais são duas telas, mas uma tabela
# só: a coluna CATEGORIA é que separa. Cada tela grava a sua categoria e só
# enxerga a sua — ninguém precisa escolher nada num campo.
CATEGORIA_DA_TELA = {"licencas": "LICENCA", "ambiental": "AMBIENTAL"}

# O PGRS é cadastro anual por filial: uma linha por resíduo, não por mês.
# Fica numa tabela própria porque o grão é outro — misturar com o consumo
# mensal obrigaria toda soma mensal a lembrar de excluir essas linhas.
TABELA_PGRS = "SUSTENTABILIDADE_PRGS"

# Nomes exatos como estão no Supabase — três têm espaço, não underscore.
COL_IBAMA = "CODIGO DO RESIDUO IBAMA"
COL_UNIDADE = "UNIDADE MEDIDA"
COL_LOCAL = "LOCAL GERADO"
COL_TRANSPORTE = "TRANSPORTE INTERNO"
COL_MEDIA = "MEDIA ANUAL"

# Nomes que apareciam cortados na tela do Supabase. Se algum divergir, o
# insert falha citando a coluna — corrija aqui, num lugar só.
COL_SOLIDOS = "SOLIDOS_CONTAMINADOS"
COL_OLEO = "OLEO_LUBRIFICANTE"
COL_DT_VENCIMENTO = "DT_VENCIMENTO"
COL_DIAS = "DIAS"  # dias pré-vencimento
COL_DATA_PAGAMENTO = "DATA_PAGAMENTO"
COL_BP = "BP FORNECEDOR"  # atenção: espaço no nome, não underscore

# Código SAP da filial (COD_ORG_VENDAS), presente nas 5 tabelas. É ele, e
# não o nome, que define o que cada usuário enxerga: o nome era escrito de
# 98 formas diferentes ('CUBATÃO', 'Cubatão', 'cubatão') e a comparação do
# PostgREST é por texto exato, então 37% dos lançamentos ficavam invisíveis
# para o usuário da própria filial. Quem preenche a coluna é a trigger
# trg_cod_filial no banco — o app não escreve esse campo.
COL_COD_FILIAL = "COD_FILIAL"

# Esgoto não tinha coluna nenhuma; água e energia tinham só a medição.
# O valor em R$ existe apenas para as três utilidades: o dinheiro dos
# resíduos já vive em SUSTENTABILIDADE_CUSTO (saída) e em
# SUSTENTABILIDADE_RECICLAVEIS (entrada), e duas fontes para o mesmo
# número sempre divergem.
COL_ESGOTO = "ESGOTO_M3"
COL_ESGOTO_VALOR = "ESGOTO_VALOR"
COL_AGUA_VALOR = "AGUA_VALOR"
COL_ENERGIA_VALOR = "ENERGIA_VALOR"

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

    Admin vê tudo; os demais recebem um filtro por COD_FILIAL. O recorte é
    pelo código, não pelo nome: o `.in_()` compara texto exato no servidor,
    e qualquer diferença de acento, caixa ou espaço no nome fazia a linha
    desaparecer para quem era daquela filial.
    """
    cliente = conectar_supabase()
    consulta = cliente.table(TABELAS_DB[tabela_app]).select("*")
    if tabela_app in CATEGORIA_DA_TELA:
        consulta = consulta.eq("CATEGORIA", CATEGORIA_DA_TELA[tabela_app])
    if not PERFIL["admin"]:
        consulta = consulta.in_(COL_COD_FILIAL, PERFIL["codigos"])
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
NOMES_COD_FILIAL = {"CODFILIAL", "CODIGOFILIAL", "CODORGVENDAS"}

# Colunas do cadastro que alimentam o cabeçalho do PGRS. Cada uma pode não
# existir ainda — o app trata a ausência como campo em branco, não como erro.
NOMES_NOME = {"NOME", "NOMECOMPLETO", "NOMEUSUARIO"}
NOMES_CARGO = {"CARGO", "FUNCAO", "FUNÇÃO"}
NOMES_ENDERECO = {"ENDERECO", "ENDEREÇO", "LOGRADOURO"}
NOMES_MUNICIPIO = {"MUNICIPIO", "MUNICÍPIO", "CIDADE"}
NOMES_UF = {"UF", "ESTADO"}
NOMES_CEP = {"CEP"}
NOMES_TELEFONE = {"TELEFONE", "FONE", "TEL"}

# chave do cabeçalho -> nomes aceitos da coluna. A separação importa: os
# de cima descrevem a FILIAL e se repetem em cada usuário dela; os de
# baixo descrevem a PESSOA que está gerando o documento.
COLUNAS_DA_FILIAL = {
    "endereco": NOMES_ENDERECO,
    "municipio": NOMES_MUNICIPIO,
    "uf": NOMES_UF,
    "cep": NOMES_CEP,
    "telefone": NOMES_TELEFONE,
}
# Nome, cargo e e-mail vêm do Azure — o diretório da empresa é a fonte
# certa para eles, e fica sempre em dia sem ninguém manter cadastro. O
# cadastro entra só como rede, para o caso de o AD não ter jobTitle.
COLUNAS_DA_PESSOA = {
    "responsavel": NOMES_NOME,
    "cargo": NOMES_CARGO,
    "email": NOMES_EMAIL,
}


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


def codigos_limpos(serie) -> list:
    """COD_FILIAL é texto de 4 dígitos e precisa continuar sendo.

    Se a coluna tiver sido criada como número em algum lugar do caminho, o
    valor chega como 1 ou 1.0 e deixa de casar com '0001' no banco — o
    zfill devolve os zeros à esquerda antes da comparação.
    """
    vistos = set()
    for bruto in serie.dropna():
        texto = str(bruto).strip()
        if texto.endswith(".0"):
            texto = texto[:-2]
        if not texto:
            continue
        vistos.add(texto.zfill(4) if texto.isdigit() else texto.upper())
    return sorted(vistos)


def perfil_acesso(email: str) -> dict:
    """Devolve o que este e-mail pode ver."""
    email = (email or "").strip().lower()
    admin = email in ADMINS
    perfil = {
        "email": email,
        "admin": admin,
        "ok": admin,
        "filiais": [],   # nomes — só para exibir na tela
        "codigos": [],   # COD_FILIAL — é o que filtra de verdade
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
    col_cod = acha_coluna(df.columns, NOMES_COD_FILIAL)
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
    if col_cod is not None:
        perfil["codigos"] = codigos_limpos(minhas[col_cod])
    if col_cnpj is not None:
        perfil["cnpjs"] = valores_limpos(minhas[col_cnpj])

    if not admin:
        # Sem código não há como filtrar, e cair de volta no nome traria
        # de volta o problema que o COD_FILIAL veio resolver. Melhor barrar
        # dizendo o que falta do que mostrar meia base sem avisar.
        if col_cod is None:
            perfil["erro"] = (
                f"{TABELA_USUARIOS} não tem a coluna {COL_COD_FILIAL}. "
                f"Colunas encontradas: {list(df.columns)}"
            )
        elif perfil["filiais"] and not perfil["codigos"]:
            perfil["erro"] = (
                f"seu cadastro em {TABELA_USUARIOS} está com "
                f"{COL_COD_FILIAL} vazio para "
                + (", ".join(perfil["filiais"]) or "a filial")
            )
        perfil["ok"] = bool(perfil["codigos"])
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


def entrada_filial(chave: str, label: str = "FILIAL", on_change=None, args=None) -> None:
    """Campo FILIAL como lista fechada, com texto livre como último recurso.

    on_change existe para as telas que preenchem outros campos a partir da
    filial escolhida. O callback roda ANTES do rerun, que é o único momento
    em que dá para escrever na key de um widget sem o Streamlit reclamar.
    """
    opcoes = opcoes_filial()
    if not opcoes:
        st.text_input(
            label,
            key=chave,
            help=f"{TABELA_USUARIOS} não devolveu filiais — digite manualmente",
            on_change=on_change,
            args=args or (),
        )
        return
    st.selectbox(label, opcoes, key=chave, on_change=on_change, args=args or ())


def codigo_da_filial(nome) -> str:
    """Nome escolhido no formulário -> COD_FILIAL, pelo cadastro de usuários.

    É a tradução que permite cruzar o formulário com o histórico: as bases
    antigas têm 98 grafias para 43 filiais, então casar por nome erraria.
    """
    alvo = str(nome or "").strip().upper()
    if not alvo:
        return ""
    try:
        df = carregar_usuarios()
    except Exception:
        return ""
    col_filial = acha_coluna(df.columns, NOMES_FILIAL)
    col_cod = acha_coluna(df.columns, NOMES_COD_FILIAL)
    if df.empty or col_filial is None or col_cod is None:
        return ""
    iguais = df[col_filial].astype(str).str.strip().str.upper() == alvo
    codigos = codigos_limpos(df[iguais][col_cod])
    return codigos[0] if codigos else ""


# ------------------------------------------------
# Telas restritas
# ------------------------------------------------
# A tela de Indicadores é só para os e-mails da lista ADMINS. Quem entra
# pelo cadastro de SUSTENTABILIDADE_USUARIOS não tem acesso — nem pelo
# cartão do menu, nem chegando direto na tela.
#
# São DUAS camadas de propósito: esconder o cartão é conveniência, não
# proteção. A verificação dentro da tela é o que de fato barra, e é ela que
# garante que nenhuma consulta ao banco acontece antes da checagem.
TELAS_RESTRITAS = {"indicador"}


def pode_ver(tela: str) -> bool:
    return PERFIL["admin"] or tela not in TELAS_RESTRITAS


# ------------------------------------------------
# Porteiro: aqui o acesso é decidido
# ------------------------------------------------
PERFIL = perfil_acesso(usuario_email_logado)

if not PERFIL["ok"]:
    st.error(
        "Acesso não autorizado. Seu e-mail não está na lista do painel nem "
        f"cadastrado em {TABELA_USUARIOS} com um {COL_COD_FILIAL}."
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
    "ambiental": "🌿 CONTROLES AMBIENTAIS",
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
     "Gerencie e acompanhe as licenças e documentações obrigatórias."),
    ("ambiental", "CONTROLES<br>AMBIENTAIS", SVG_FOLHA, "verde",
     "Acompanhe os controles ambientais periódicos de cada filial."),
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
    # o cartão de tela restrita simplesmente não é oferecido
    visiveis = [c for c in CARDS_MENU if pode_ver(c[0])]
    for i, (tela, titulo, icone, cor, descricao) in enumerate(visiveis):
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
    "con_agua_valor",
    "con_esgoto",
    "con_esgoto_valor",
    "con_energia",
    "con_energia_valor",
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
        COL_AGUA_VALOR: st.session_state.get("con_agua_valor", 0.0),
        COL_ESGOTO: st.session_state.get("con_esgoto", 0.0),
        COL_ESGOTO_VALOR: st.session_state.get("con_esgoto_valor", 0.0),
        "ENERGIA": st.session_state.get("con_energia", 0.0),
        COL_ENERGIA_VALOR: st.session_state.get("con_energia_valor", 0.0),
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

    # As utilidades vêm em par — medição e conta — e o par fica lado a
    # lado de propósito: quem digita está olhando a mesma fatura, e ver os
    # dois juntos é o que permite notar m³ alto com valor baixo (ou o
    # contrário) na hora do lançamento, não três meses depois no gráfico.
    st.markdown("**Utilidades** — medição e valor da conta")
    med, val = st.columns(2)
    with med:
        st.number_input("ÁGUA (m³)", min_value=0.0, step=0.01, format="%.2f", key="con_agua")
        st.number_input("ESGOTO (m³)", min_value=0.0, step=0.01, format="%.2f", key="con_esgoto")
        st.number_input("ENERGIA (kWh)", min_value=0.0, step=0.01, format="%.2f", key="con_energia")
    with val:
        st.number_input("ÁGUA (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_agua_valor")
        st.number_input("ESGOTO (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_esgoto_valor")
        st.number_input("ENERGIA (R$)", min_value=0.0, step=0.01, format="%.2f", key="con_energia_valor")

    st.markdown("**Resíduos e demais** — só medição")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input("SÓLIDOS CONTAMINADOS (kg)", min_value=0.0, step=0.01, format="%.2f", key="con_solidos")
        st.number_input("MADEIRA (kg)", min_value=0.0, step=0.01, format="%.2f", key="con_madeira")
    with c2:
        st.number_input("ÓLEO LUBRIFICANTE (L)", min_value=0.0, step=0.01, format="%.2f", key="con_oleo")
        st.number_input("RECICLÁVEIS (kg)", min_value=0.0, step=0.01, format="%.2f", key="con_reciclaveis")
    with c3:
        st.number_input("COMUM (kg)", min_value=0.0, step=0.01, format="%.2f", key="con_comum")
        st.number_input("CO² (t)", min_value=0.0, step=0.01, format="%.2f", key="con_co2")

    st.button("💾 Salvar", key="btn_salvar_con", on_click=salvar_consumo, type="primary")
    render_msg("msg_consumos")


# ================================================
# 2) CONTROLE DE LICENÇAS  ->  SUSTENTABILIDADE_LICENCAS
# ================================================
CATEGORIAS_LICENCA = ["LICENCA", "AMBIENTAL"]

# ------------------------------------------------------------
# O que a tela consegue preencher sozinha
# ------------------------------------------------------------
# Duas leituras da própria tabela, em cache de 5 min: a lista de nomes já
# usados em cada categoria, e o CNPJ/ROTA que cada filial mais usa. Nenhuma
# coluna nova — é o histórico respondendo pelo que se repete.
CONTROLE_OUTRO = "OUTRO — digitar"


def chave_nome(texto) -> str:
    """Nome sem acento e sem caixa, para reconhecer a mesma coisa escrita
    de dois jeitos."""
    limpo = unicodedata.normalize("NFKD", str(texto))
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    return " ".join(limpo.upper().split())


def mais_frequente(contagem: dict):
    """A grafia mais usada; empate resolve pelo alfabeto, para não variar
    entre execuções."""
    return max(sorted(contagem), key=contagem.get) if contagem else None


@st.cache_data(ttl=300, show_spinner=False)
def catalogo_controles() -> dict:
    """Nomes já lançados em cada categoria, uma grafia por nome.

    'Caixa de Esgoto' (16x) e 'Caixa de esgoto' (12x) são o mesmo controle:
    a lista fica com a grafia mais usada. Sem essa deduplicação a lista
    suspensa nasceria com o item repetido — que é justamente o problema que
    ela vem resolver.

    A leitura é da tabela inteira, sem o recorte de filial: aqui não há dado
    de lançamento, só o nome do tipo de controle, e uma filial nova
    começaria com a lista vazia se dependesse dos próprios registros.
    """
    try:
        cliente = conectar_supabase()
        resposta = (
            cliente.table(TABELAS_DB["licencas"])
            .select("CATEGORIA,LICENCA")
            .limit(5000)
            .execute()
        )
    except Exception:
        return {}

    vistos = {}
    for linha in resposta.data or []:
        nome = str(linha.get("LICENCA") or "").strip()
        categoria = str(linha.get("CATEGORIA") or "").strip().upper()
        if not nome or not categoria:
            continue
        grafias = vistos.setdefault(categoria, {}).setdefault(chave_nome(nome), {})
        grafias[nome] = grafias.get(nome, 0) + 1

    return {
        categoria: sorted(mais_frequente(g) for g in por_chave.values())
        for categoria, por_chave in vistos.items()
    }


def opcoes_controle(tela: str) -> list:
    return catalogo_controles().get(CATEGORIA_DA_TELA[tela], [])


# ROTA e CNPJ não são consultados: são DERIVADOS do código da filial.
#
# A primeira versão tirava os dois do histórico, pegando o valor mais usado
# por filial. Errava: a Matriz tinha 'ROTA 0.001' em 13 linhas (a planilha
# de origem formatou '0001' como número) e a Pavuna tinha '36' em 10. O
# valor mais frequente pode ser o erro mais frequente.
#
# Medido contra as 784 linhas da base: a rota é o código sem os zeros à
# esquerda em 92% delas, e o CNPJ é a raiz da empresa + o código + dígito
# verificador em 99,6% — os 39 CNPJs distintos da Della Volpe conferem sem
# exceção. Derivar acerta 100%, inclusive nas 4 filiais que ainda não têm
# nenhum lançamento e que o histórico não teria como responder.
RAIZ_CNPJ = "61139432"
_PESOS_CNPJ = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def digitos_cnpj(base12: str) -> str:
    """Os dois dígitos verificadores, pelo módulo 11 da Receita."""
    numeros = [int(c) for c in base12]
    verificadores = []
    for pesos in (_PESOS_CNPJ, [6] + _PESOS_CNPJ):
        soma = sum(n * p for n, p in zip(numeros + verificadores, pesos))
        resto = soma % 11
        verificadores.append(0 if resto < 2 else 11 - resto)
    return "".join(str(d) for d in verificadores)


def cnpj_da_filial(codigo: str) -> str:
    """'0001' -> '61.139.432/0001-72'."""
    codigo = str(codigo or "").strip()
    if not codigo.isdigit():
        return ""
    base = RAIZ_CNPJ + codigo.zfill(4)
    d = digitos_cnpj(base)
    return f"{base[:2]}.{base[2:5]}.{base[5:8]}/{base[8:12]}-{d}"


def rota_da_filial(codigo: str) -> str:
    """'0001' -> '1'; a rota é o código sem os zeros à esquerda."""
    codigo = str(codigo or "").strip()
    return str(int(codigo)) if codigo.isdigit() else ""
OPCOES_STATUS = ["NO PRAZO", "VENCIDO", "RENOVAR", "NÃO SE APLICA"]
TIPOS_EVIDENCIA = ["png", "jpg", "jpeg", "pdf"]
# As duas telas usam o mesmo formulário. O prefixo é o que as separa: a
# key de um widget é global no session_state, então sem prefixos distintos
# o que fosse digitado em Licenças reapareceria em Ambientais.
PREFIXO_LICENCA = {"licencas": "lic", "ambiental": "amb"}

CAMPOS_LICENCA_BASE = (
    "filial",
    "rota",
    "cnpj",
    "licenca",
    "licenca_novo",
    "dt_venc",
    "dias_pre",
    "status",
    "obs",
)


def campos_licenca(tela: str) -> tuple:
    prefixo = PREFIXO_LICENCA[tela]
    return tuple(f"{prefixo}_{campo}" for campo in CAMPOS_LICENCA_BASE)


@st.cache_data(ttl=300, show_spinner=False)
def catalogo_residuos() -> dict:
    """Resíduo -> (código IBAMA, classe, unidade), do que já foi lançado.

    A lista fixa RESIDUOS_PGRS é semente: cobre os 11 da Matriz. Quem
    lançar um resíduo novo em qualquer filial passa a alimentar o
    preenchimento automático das próximas, sem redeploy.

    A chave é o nome normalizado (sem acento, sem caixa), então
    'Óleo Lubrificante' e 'OLEO LUBRIFICANTE' são o mesmo resíduo. Para
    cada campo vale a grafia mais usada — uma linha com a classe errada
    não contamina o preenchimento.
    """
    catalogo = {
        chave_nome(nome): {"nome": nome, COL_IBAMA: {codigo: 1},
                           "CLASSE": {classe: 1}, COL_UNIDADE: {unidade: 1}}
        for nome, (codigo, classe, unidade) in RESIDUOS_PGRS.items()
    }

    try:
        cliente = conectar_supabase()
        resposta = (
            cliente.table(TABELA_PGRS)
            .select(f'"RESIDUO","{COL_IBAMA}","CLASSE","{COL_UNIDADE}"')
            .limit(5000)
            .execute()
        )
        linhas = resposta.data or []
    except Exception:
        linhas = []

    for linha in linhas:
        nome = str(linha.get("RESIDUO") or "").strip()
        if not nome:
            continue
        registro = catalogo.setdefault(
            chave_nome(nome),
            {"nome": nome, COL_IBAMA: {}, "CLASSE": {}, COL_UNIDADE: {}},
        )
        for coluna in (COL_IBAMA, "CLASSE", COL_UNIDADE):
            valor = str(linha.get(coluna) or "").strip()
            if valor:
                registro[coluna][valor] = registro[coluna].get(valor, 0) + 1

    return {
        chave: (
            registro["nome"],
            mais_frequente(registro[COL_IBAMA]) or "",
            mais_frequente(registro["CLASSE"]) or "",
            mais_frequente(registro[COL_UNIDADE]) or "",
        )
        for chave, registro in catalogo.items()
    }


def opcoes_residuo() -> list:
    """Nomes oferecidos na lista, sem repetir grafia."""
    return sorted(nome for nome, _, _, _ in catalogo_residuos().values())


def preenche_pelo_residuo() -> None:
    """Código IBAMA, classe e unidade do resíduo escolhido.

    Precisa ser callback, não `value=` no text_input: uma vez que a key
    existe no session_state, o Streamlit ignora o argumento `value` e o
    campo congela no primeiro valor. O on_change roda antes do rerun, que
    é o único momento em que dá para escrever na key de um widget.
    """
    dados = catalogo_residuos().get(chave_nome(nome_residuo()))
    if not dados:
        return
    _, codigo, classe, unidade = dados
    st.session_state["pgrs_ibama"] = codigo
    st.session_state["pgrs_classe"] = classe
    st.session_state["pgrs_unidade"] = unidade


def nome_controle(tela: str) -> str:
    """O nome escolhido na lista, ou o digitado quando a opção é OUTRO."""
    prefixo = PREFIXO_LICENCA[tela]
    escolhido = txt(f"{prefixo}_licenca")
    if escolhido == CONTROLE_OUTRO:
        return txt(f"{prefixo}_licenca_novo")
    return escolhido


def preenche_pela_filial(tela: str) -> None:
    """CNPJ e ROTA da filial escolhida, calculados do COD_FILIAL.

    Preenche, não trava: os dois campos continuam editáveis, porque existe
    exceção real — há lançamento com CNPJ de outra empresa (a Splenda, na
    Matriz), que não sai da raiz da Della Volpe.
    """
    prefixo = PREFIXO_LICENCA[tela]
    codigo = codigo_da_filial(st.session_state.get(f"{prefixo}_filial"))
    st.session_state[f"{prefixo}_cnpj"] = cnpj_da_filial(codigo)
    st.session_state[f"{prefixo}_rota"] = rota_da_filial(codigo)


# O file_uploader não zera ao apagar a key; troca-se a própria key por uma
# nova (contador) para o widget nascer vazio no próximo registro.
for _prefixo in PREFIXO_LICENCA.values():
    st.session_state.setdefault(f"{_prefixo}_upload_n", 0)


def chave_evidencia(tela: str) -> str:
    prefixo = PREFIXO_LICENCA[tela]
    return f"{prefixo}_evidencia_{st.session_state[f'{prefixo}_upload_n']}"


def salvar_licenca(tela: str = "licencas") -> None:
    prefixo = PREFIXO_LICENCA[tela]
    chave_msg = f"msg_{tela}"
    rotulo = "Licença" if tela == "licencas" else "Controle ambiental"
    arquivo = st.session_state.get(chave_evidencia(tela))

    nome = nome_controle(tela)

    faltando = []
    if not txt(f"{prefixo}_filial"):
        faltando.append("FILIAL")
    if not nome:
        faltando.append(rotulo.upper())
    if arquivo is None:
        faltando.append(f"{rotulo} (evidência)")
    if faltando:
        st.session_state[chave_msg] = ("warning", "Obrigatório: " + ", ".join(faltando))
        return

    # A evidência não vai no payload: o vínculo é o nome do objeto no MinIO
    # (<id>_<n>.<ext>), que listar_anexos() encontra pelo prefixo.
    dados = {
        "FILIAL": txt(f"{prefixo}_filial").upper(),
        "ROTA": txt(f"{prefixo}_rota"),  # coluna text no banco
        "CNPJ": txt(f"{prefixo}_cnpj"),
        "LICENCA": nome,
        COL_DT_VENCIMENTO: st.session_state.get(f"{prefixo}_dt_venc", date.today()),
        COL_DIAS: int(st.session_state.get(f"{prefixo}_dias_pre", 0)),
        "STATUS": st.session_state.get(f"{prefixo}_status", OPCOES_STATUS[0]),
        "OBSERVACAO": txt(f"{prefixo}_obs"),
        # quem define a categoria é a tela, não um campo que o usuário possa
        # errar — é ela que decide em qual das duas o registro vai aparecer
        "CATEGORIA": CATEGORIA_DA_TELA[tela],
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
        return f"{rotulo} {id_registro} salvo · evidência em {BUCKET_LICENCAS}/{objeto}"

    def limpar_upload() -> None:
        st.session_state[f"{prefixo}_upload_n"] += 1

    concluir(
        chave_msg,
        tela,
        dados,
        campos_licenca(tela),
        apos_ok=limpar_upload,
        apos_insert=subir,
    )


def form_licencas(tela: str = "licencas") -> None:
    prefixo = PREFIXO_LICENCA[tela]
    rotulo = "LICENÇA" if tela == "licencas" else "CONTROLE"

    opcoes = opcoes_controle(tela)

    c1, c2, c3 = st.columns(3)
    with c1:
        entrada_filial(
            f"{prefixo}_filial",
            on_change=preenche_pela_filial,
            args=(tela,),
        )
        # primeira abertura da tela: o on_change ainda não disparou, então a
        # sugestão é aplicada aqui, depois que o selectbox já existe
        if f"{prefixo}_cnpj" not in st.session_state:
            preenche_pela_filial(tela)

        if opcoes:
            escolha = st.selectbox(
                rotulo,
                opcoes + [CONTROLE_OUTRO],
                key=f"{prefixo}_licenca",
                help="Lista montada com o que já foi lançado, para o nome não "
                     "variar entre registros",
            )
            if escolha == CONTROLE_OUTRO:
                st.text_input(
                    f"Qual {rotulo.lower()}?",
                    key=f"{prefixo}_licenca_novo",
                    placeholder="nome novo",
                )
        else:
            st.text_input(rotulo, key=f"{prefixo}_licenca")
        st.selectbox("STATUS", OPCOES_STATUS, key=f"{prefixo}_status")
    with c2:
        st.text_input(
            "ROTA",
            key=f"{prefixo}_rota",
            help="Calculada pelo código da filial; corrija se for outra",
        )
        st.date_input(
            "DT VENCIMENTO",
            value=date.today(),
            format="DD/MM/YYYY",
            key=f"{prefixo}_dt_venc",
        )
        st.number_input(
            "DIAS PRÉ VENCIMENTO",
            min_value=0,
            step=1,
            format="%d",
            key=f"{prefixo}_dias_pre",
        )
    with c3:
        st.text_input(
            "CNPJ",
            key=f"{prefixo}_cnpj",
            help="Calculado pelo código da filial; corrija se for outro",
        )

    st.text_area("OBSERVAÇÃO", key=f"{prefixo}_obs")

    st.markdown("**Evidência (obrigatória)**")
    esq, dir_ = st.columns([2, 1])
    with esq:
        arquivo = st.file_uploader(
            rotulo.capitalize(),
            type=TIPOS_EVIDENCIA,
            key=chave_evidencia(tela),
            help=f"Imagem ou PDF. Sem o anexo o registro não é salvo.",
        )
    with dir_:
        if arquivo is not None:
            if str(arquivo.type).startswith("image/"):
                st.image(arquivo, caption=arquivo.name, width=200)
            else:
                st.success(f"📎 {arquivo.name} · {arquivo.size / 1024:,.1f} KB")

    st.button(
        "💾 Salvar",
        key=f"btn_salvar_{prefixo}",
        on_click=salvar_licenca,
        args=(tela,),
        disabled=arquivo is None,
        type="primary",
    )
    if arquivo is None:
        st.caption(f"Anexe a evidência para liberar o Salvar.")

    render_msg(f"msg_{tela}")


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
        campo(COL_SOLIDOS, "decimal", "SÓLIDOS CONTAMINADOS (kg)"),
        campo(COL_OLEO, "decimal", "ÓLEO LUBRIFICANTE (L)"),
        campo("AGUA", "decimal", "ÁGUA (m³)"),
        campo(COL_AGUA_VALOR, "decimal", "ÁGUA (R$)"),
        campo(COL_ESGOTO, "decimal", "ESGOTO (m³)"),
        campo(COL_ESGOTO_VALOR, "decimal", "ESGOTO (R$)"),
        campo("ENERGIA", "decimal", "ENERGIA (kWh)"),
        campo(COL_ENERGIA_VALOR, "decimal", "ENERGIA (R$)"),
        campo("COMUM", "decimal", "COMUM (kg)"),
        campo("MADEIRA", "decimal", "MADEIRA (kg)"),
        campo("RECICLAVEIS", "decimal", "RECICLÁVEIS (kg)"),
        campo("CO2", "decimal", "CO² (t)"),
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
    # mesma tabela, mesmos campos: a CATEGORIA continua editável de
    # propósito, para reclassificar um registro que caiu na tela errada
    "ambiental": [
        campo("FILIAL", "filial"),
        campo("LICENCA", "texto", "CONTROLE"),
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
    "ambiental": ("FILIAL", "LICENCA", COL_DT_VENCIMENTO),
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
    "ambiental": ("FILIAL", "LICENCA"),
    "custos": ("FILIAL", "FORNECEDOR"),
    "reciclaveis": ("FILIAL", "MATERIAL"),
    "pgrs": ("FILIAL", "RESIDUO"),
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


# ------------------------------------------------
# PGRS — Plano de Gerenciamento de Resíduos Sólidos
# ------------------------------------------------
# Documento anual por filial: uma linha por resíduo, com os atributos do
# resíduo (código IBAMA, classe, acondicionamento, destinação...) e a média
# anual. Dos 14 campos, 13 não mudam de um ano para o outro — só a média.
PAGINAS_CONSUMOS = {
    "lancamento": "Consumos e Serviços",
    "pgrs": "PGRS — Resíduos",
}

# Até 2019 é o alcance da base de consumo; o ano que vem entra porque o
# PGRS costuma ser montado antes do ano fechar.
def anos_pgrs() -> list:
    atual = date.today().year
    return list(range(atual + 1, 2018, -1))


# De qual coluna de CONSUMO sai a média de cada resíduo. A chave é o
# começo do nome normalizado, porque o nome no documento é mais longo que
# o do app: "Recicláveis Papel/ Papelão/Plastico" -> RECICLAVEIS,
# "Sólidos contaminados (Panos/Estopas..)" -> SOLIDOS_CONTAMINADOS.
#
# Dos 11 resíduos da Matriz, só estes 5 têm origem no app. Lona de freio,
# lâmpadas, eletrônicos, baterias, pneu e borra de tinta não são medidos
# em lugar nenhum do sistema — para eles a média continua digitada.
ORIGEM_DO_RESIDUO = {
    "COMUM": "COMUM",
    "MADEIRA": "MADEIRA",
    "RECICLAVEIS": "RECICLAVEIS",
    "RECICLAVEL": "RECICLAVEIS",
    "SOLIDOS": COL_SOLIDOS,
    "OLEO": COL_OLEO,
}


def coluna_do_residuo(residuo) -> str:
    """Nome do resíduo no PGRS -> coluna de CONSUMO, ou '' se não houver."""
    chave = chave_nome(residuo)
    if not chave:
        return ""
    for prefixo, coluna in ORIGEM_DO_RESIDUO.items():
        if chave.startswith(prefixo):
            return coluna
    return ""


@st.cache_data(ttl=300, show_spinner=False)
def medias_do_ano(codigo_filial: str, ano: int) -> dict:
    """Média anual de cada coluna de CONSUMO: soma do ano dividida por 12.

    Doze, sempre — não a média dos meses lançados. É o que o documento da
    Matriz faz: o óleo lubrificante tem 3 meses lançados em 2025 somando
    5.500 L, e o PGRS registra 458,33, que é 5.500/12. Dividir pelos meses
    presentes daria 1.833,33 e quadruplicaria o número justamente no
    resíduo mais irregular.
    """
    if not codigo_filial:
        return {}
    try:
        cliente = conectar_supabase()
        resposta = (
            cliente.table(TABELAS_DB["consumos"])
            .select("*")
            .eq(COL_COD_FILIAL, codigo_filial)
            .eq("ANO", int(ano))
            .limit(LIMITE_REGISTROS)
            .execute()
        )
    except Exception:
        return {}

    df = pd.DataFrame(resposta.data or [])
    if df.empty:
        return {}

    medias = {}
    for coluna in set(ORIGEM_DO_RESIDUO.values()):
        if coluna in df.columns:
            soma = pd.to_numeric(df[coluna], errors="coerce").fillna(0).sum()
            medias[coluna] = float(soma) / 12
    return medias


def media_anual_calculada(residuo, codigo_filial: str, ano: int):
    """A média do resíduo, ou None quando ele não é medido no app."""
    coluna = coluna_do_residuo(residuo)
    if not coluna:
        return None
    return medias_do_ano(codigo_filial, ano).get(coluna)


# Código IBAMA, classe e unidade são fixos por resíduo: escolher o resíduo
# preenche os três. Lista tirada do PGRS da Matriz.
RESIDUOS_PGRS = {
    "Lona de freio": ("160112", "I", "KG"),
    "Comum": ("-", "II", "KG"),
    "Óleo Lubrificante": ("130201", "I", "LT"),
    "Recicláveis Papel/Papelão/Plástico": ("1501", "II A", "KG"),
    "Lâmpadas Fluorescentes": ("200121", "II A", "UN"),
    "Eletrônicos": ("200136", "II B", "KG"),
    "Baterias automotivas": ("F042", "I", "UN"),
    "Pneu": ("160126", "II A", "KG"),
    "Sólidos contaminados (Panos/Estopas)": ("190204", "I", "KG"),
    "Borra de tinta": ("F017", "I", "LT"),
    "Madeira": ("150103", "II B", "KG"),
}

FREQUENCIAS_PGRS = ["Sob Demanda", "1x semana", "2x semana", "3x semana",
                    "Quinzenal", "Mensal", "Trimestral", "Semestral", "Anual"]

# A aba Editar/Excluir usa a mesma maquinaria das outras telas — ela lê
# CAMPOS_EDICAO pela chave da tela. Sem esta entrada o painel carregava os
# registros e não desenhava campo nenhum: dava para excluir, não para
# editar. Fica aqui embaixo, e não junto das outras, porque depende de
# FREQUENCIAS_PGRS, definida logo acima.
CAMPOS_EDICAO["pgrs"] = [
    campo("FILIAL", "filial"),
    campo("ANO", "inteiro", minimo=1990, maximo=2100),
    campo("RESIDUO", "texto", "RESÍDUO"),
    campo(COL_IBAMA, "texto", "CÓDIGO IBAMA"),
    campo("CLASSE", "texto"),
    campo(COL_UNIDADE, "texto", "UNIDADE"),
    campo(COL_LOCAL, "texto", "LOCAL GERADO"),
    campo("ACONDICIONAMENTO", "texto"),
    campo(COL_TRANSPORTE, "texto", "TRANSPORTE INTERNO"),
    campo("RESPONSAVEL", "texto", "RESPONSÁVEL"),
    campo("ARMAZENAGEM", "texto"),
    campo("COLETA", "texto"),
    campo("DESTINACAO", "texto", "DESTINAÇÃO"),
    campo("FREQUENCIA", "opcoes", "FREQUÊNCIA", opcoes=FREQUENCIAS_PGRS),
]

RESUMO_REGISTRO["pgrs"] = ("FILIAL", "ANO", "RESIDUO")


# Colunas cujo valor se repete mas não cabe em lista fixa: coleta e
# destinação dependem do fornecedor contratado, que muda. Vão como lista
# aberta — montada com o que já foi lançado, mais "OUTRO — digitar".
COLUNAS_ABERTAS_PGRS = (
    COL_LOCAL,
    "ACONDICIONAMENTO",
    COL_TRANSPORTE,
    "RESPONSAVEL",
    "ARMAZENAGEM",
    "COLETA",
    "DESTINACAO",
)

# Ponto de partida de cada lista aberta, para a primeira filial não começar
# com o campo em branco. Depois o histórico manda.
SEMENTES_PGRS = {
    COL_LOCAL: ["Manutenção", "Operação", "Escritórios", "Todos"],
    "ACONDICIONAMENTO": ["Tambor", "Caçamba", "Gaiolas", "Caixas"],
    COL_TRANSPORTE: ["Ajudante mecânica", "Ajudante geral", "Ajudante Borracharia",
                     "Limpeza terceirizada", "Manutenção Predial", "T.I"],
    "RESPONSAVEL": ["Meio Ambiente"],
    "ARMAZENAGEM": ["Central de resíduos", "Caçamba"],
    "COLETA": [],
    "DESTINACAO": ["Aterro", "Reciclagem", "Rerrefino", "Alternativa Ambiental"],
}


@st.cache_data(ttl=300, show_spinner=False)
def catalogo_pgrs() -> dict:
    """Valores já usados em cada coluna aberta, uma grafia por valor.

    Mesma deduplicação da lista de controles: 'Recliclagem' e 'reciclagem'
    seriam dois destinos diferentes numa lista ingênua. A planilha de
    origem já tinha esse par, além de 'Caçamba'/'Caçambas'.
    """
    try:
        cliente = conectar_supabase()
        resposta = (
            cliente.table(TABELA_PGRS)
            .select(",".join(f'"{c}"' for c in COLUNAS_ABERTAS_PGRS))
            .limit(5000)
            .execute()
        )
    except Exception:
        resposta = types_vazio()

    vistos = {c: {} for c in COLUNAS_ABERTAS_PGRS}
    for linha in getattr(resposta, "data", None) or []:
        for coluna in COLUNAS_ABERTAS_PGRS:
            valor = str(linha.get(coluna) or "").strip()
            if valor:
                grafias = vistos[coluna].setdefault(chave_nome(valor), {})
                grafias[valor] = grafias.get(valor, 0) + 1

    catalogo = {}
    for coluna in COLUNAS_ABERTAS_PGRS:
        nomes = {mais_frequente(g) for g in vistos[coluna].values()}
        nomes.update(SEMENTES_PGRS.get(coluna, []))
        catalogo[coluna] = sorted(n for n in nomes if n)
    return catalogo


def types_vazio():
    """Resposta vazia no formato do cliente, para a tela abrir sem tabela."""
    import types as _t

    return _t.SimpleNamespace(data=[])


def entrada_aberta(coluna: str, chave: str, label: str = None) -> None:
    """Selectbox com o que já existe + OUTRO para digitar um valor novo."""
    opcoes = catalogo_pgrs().get(coluna, [])
    label = label or coluna
    escolha = st.selectbox(label, opcoes + [CONTROLE_OUTRO], key=chave)
    if escolha == CONTROLE_OUTRO:
        st.text_input(f"Qual {label.lower()}?", key=f"{chave}_novo",
                      placeholder="valor novo")


def valor_aberto(chave: str) -> str:
    escolhido = txt(chave)
    return txt(f"{chave}_novo") if escolhido == CONTROLE_OUTRO else escolhido


# ------------------------------------------------
# O cabeçalho do documento
# ------------------------------------------------
# Estes campos não existem em tabela nenhuma e não vamos criar coluna para
# eles. Ficam como preenchimento de tela: quem gera o documento confere e
# ajusta, e o session_state segura os valores durante a sessão. Razão
# social e CNPJ são derivados — o CNPJ sai do código da filial.
RAZAO_SOCIAL = "Transportes Della Volpe S/A"

CAMPOS_CABECALHO = [
    ("endereco", "Endereço"),
    ("municipio", "Município"),
    ("uf", "UF"),
    ("cep", "CEP"),
    ("telefone", "Telefone"),
    ("email", "E-mail"),
    ("responsavel", "Responsável Legal"),
    ("cargo", "Cargo"),
    ("atividade", "Discriminação da Atividade"),
    ("licenca", "Licença de Operação"),
    ("validade", "Validade"),
    ("orgao", "Órgão expedidor"),
]

# O que já se sabe da Matriz, tirado do PGRS atual. Outras filiais começam
# em branco até alguém preencher uma vez.
CABECALHO_CONHECIDO = {
    "0001": {
        "endereco": "Rua: Lídice nº 22 — Parque Novo Mundo",
        "municipio": "São Paulo",
        "uf": "SP",
        "cep": "02174-010",
        "telefone": "(11) 2967-8573",
        "email": "Juliana.mendes@dellavolpe.com.br",
        "responsavel": "Juliana Mendes Barbosa",
        "cargo": "Analista Sustentabilidade",
        "atividade": "Transportes de produtos perigosos",
        "orgao": "CETESB",
    },
}

# Ordem e largura das colunas no PDF. As larguras somam 1 e são
# proporcionais à largura útil da página: coluna estreita para CLASSE,
# larga para RESÍDUO e TRANSPORTE INTERNO, que têm texto comprido.
COLUNAS_PDF = [
    ("ITEM", "ITEM", 0.03),
    (COL_IBAMA, "CÓDIGO IBAMA", 0.07),
    ("RESIDUO", "RESÍDUO", 0.13),
    ("CLASSE", "CLASSE", 0.04),
    (COL_UNIDADE, "UNIDADE", 0.05),
    (COL_MEDIA, "MÉDIA ANUAL", 0.07),
    (COL_LOCAL, "LOCAL GERADO", 0.07),
    ("ACONDICIONAMENTO", "ACONDICIO-<br/>NAMENTO", 0.08),
    (COL_TRANSPORTE, "TRANSPORTE<br/>INTERNO", 0.09),
    ("RESPONSAVEL", "RESPON-<br/>SÁVEL", 0.07),
    ("ARMAZENAGEM", "ARMAZE-<br/>NAGEM", 0.08),
    ("COLETA", "COLETA", 0.07),
    ("DESTINACAO", "DESTINAÇÃO", 0.08),
    ("FREQUENCIA", "FREQUÊNCIA", 0.07),
]

try:
    from reportlab.lib import colors as _cores_pdf
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    TEM_PDF = True
except Exception:  # pragma: no cover - depende do requirements.txt
    TEM_PDF = False


def valor_da_maioria(serie) -> str:
    """O valor mais repetido da coluna, ignorando vazios.

    Endereço, CEP e telefone descrevem a filial, mas ficam gravados em cada
    usuário dela — umas cinco cópias. Se uma linha estiver vazia ou com um
    erro de digitação, a maioria ainda devolve o valor certo, sem exigir
    que as cinco estejam idênticas.
    """
    contagem = {}
    for bruto in serie.dropna():
        texto = str(bruto).strip()
        if texto:
            contagem[texto] = contagem.get(texto, 0) + 1
    return mais_frequente(contagem) or ""


@st.cache_data(ttl=300, show_spinner=False)
def cabecalho_do_cadastro(codigo: str, email: str) -> dict:
    """Cabeçalho montado a partir de SUSTENTABILIDADE_USUARIOS.

    Colunas que ainda não existem simplesmente não aparecem no resultado —
    o campo fica em branco na tela, para ser digitado, em vez de derrubar
    a página com KeyError.
    """
    try:
        df = carregar_usuarios()
    except Exception:
        return {}
    if df.empty:
        return {}

    col_cod = acha_coluna(df.columns, NOMES_COD_FILIAL)
    col_email = acha_coluna(df.columns, NOMES_EMAIL)
    saida = {}

    if col_cod is not None and codigo:
        da_filial = df[codigos_limpos_serie(df[col_cod]) == codigo]
        for chave, nomes in COLUNAS_DA_FILIAL.items():
            coluna = acha_coluna(df.columns, nomes)
            if coluna is not None and not da_filial.empty:
                saida[chave] = valor_da_maioria(da_filial[coluna])

    if col_email is not None and email:
        iguais = df[col_email].astype(str).str.strip().str.lower() == email
        minha = df[iguais]
        for chave, nomes in COLUNAS_DA_PESSOA.items():
            coluna = acha_coluna(df.columns, nomes)
            if coluna is not None and not minha.empty:
                valor = str(minha.iloc[0][coluna] or "").strip()
                if valor:
                    saida[chave] = valor

    return {k: v for k, v in saida.items() if v}


def codigos_limpos_serie(serie):
    """codigos_limpos() devolve lista; aqui é preciso alinhar linha a linha."""
    return serie.map(lambda v: (codigos_limpos(pd.Series([v])) or [""])[0])


def cabecalho_do_azure() -> dict:
    """Nome, cargo e e-mail de quem está logado, direto do Azure AD."""
    valores = {
        "responsavel": st.session_state.get("user_name", ""),
        "cargo": st.session_state.get("user_cargo", ""),
        "email": usuario_email_logado,
    }
    return {k: v for k, v in valores.items() if v and v != "Usuário"}


def padroes_cabecalho(codigo: str) -> dict:
    """O que a tela oferece preenchido, antes de qualquer digitação.

    Precedência, do mais fraco para o mais forte: o PGRS antigo da Matriz
    (rede, some quando o cadastro estiver completo), o cadastro de
    usuários, e por último o Azure — que é o diretório da empresa e ganha
    de qualquer cópia local do nome e do cargo.
    """
    padrao = dict(CABECALHO_CONHECIDO.get(codigo, {}))
    padrao.update(cabecalho_do_cadastro(codigo, usuario_email_logado))
    padrao.update(cabecalho_do_azure())
    return padrao


def cabecalho_pgrs(codigo: str) -> dict:
    """Valores do cabeçalho: o que foi digitado, ou o que o cadastro deu."""
    padrao = padroes_cabecalho(codigo)
    return {
        chave: txt(f"pgrs_cab_{chave}") or padrao.get(chave, "")
        for chave, _ in CAMPOS_CABECALHO
    }


def form_cabecalho_pgrs(filial: str, codigo: str) -> None:
    """Os campos do cabeçalho, num expansor para não roubar a tela."""
    padrao = padroes_cabecalho(codigo)
    do_cadastro = set(cabecalho_do_cadastro(codigo, usuario_email_logado))
    do_cadastro |= set(cabecalho_do_azure())
    faltando = [r for c, r in CAMPOS_CABECALHO if not padrao.get(c)]

    with st.expander("Dados do cabeçalho do documento", expanded=bool(faltando)):
        st.caption(
            f"Razão social **{RAZAO_SOCIAL}** · CNPJ **{cnpj_da_filial(codigo)}** "
            "— derivados, não se digita. Os demais vêm do cadastro de "
            "usuários quando a coluna existe lá."
        )
        if faltando:
            st.warning(
                "Sem origem no cadastro, precisa ser digitado: "
                + ", ".join(faltando)
            )
        colunas = st.columns(3)
        for i, (chave, rotulo) in enumerate(CAMPOS_CABECALHO):
            with colunas[i % 3]:
                st.text_input(
                    rotulo + (" ·" if chave in do_cadastro else ""),
                    value=padrao.get(chave, ""),
                    key=f"pgrs_cab_{chave}",
                    help=("preenchido automaticamente — Azure ou cadastro"
                          if chave in do_cadastro else None),
                )


def pdf_pgrs(filial: str, codigo: str, ano: int, df: pd.DataFrame):
    """Monta o PDF do documento. Devolve (bytes, erro)."""
    if not TEM_PDF:
        return None, "reportlab não está instalado"

    try:
        buffer = io.BytesIO()
        largura_pagina, altura_pagina = landscape(A4)
        margem = 10 * mm
        util = largura_pagina - 2 * margem

        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=margem, rightMargin=margem,
            topMargin=margem, bottomMargin=margem,
            title=f"PGRS {filial} {ano}",
        )

        titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13,
                                textColor=_cores_pdf.HexColor("#1F7A3D"),
                                alignment=1, spaceAfter=6)
        rotulo = ParagraphStyle("r", fontName="Helvetica-Bold", fontSize=6.5,
                                textColor=_cores_pdf.HexColor("#3C4B42"))
        valor = ParagraphStyle("v", fontName="Helvetica", fontSize=7.5, leading=9)
        celula = ParagraphStyle("c", fontName="Helvetica", fontSize=6.5, leading=8)
        cabeca = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=6.5,
                                leading=8, alignment=1,
                                textColor=_cores_pdf.white)

        dados = cabecalho_pgrs(codigo)
        blocos = [
            [("Razão social", RAZAO_SOCIAL), ("CNPJ", cnpj_da_filial(codigo))],
            [("Endereço", dados["endereco"]), ("Município", dados["municipio"]),
             ("UF", dados["uf"])],
            [("CEP", dados["cep"]), ("Telefone", dados["telefone"]),
             ("E-mail", dados["email"])],
            [("Responsável Legal", dados["responsavel"]), ("Cargo", dados["cargo"])],
            [("Discriminação da Atividade", dados["atividade"])],
            [("Licença de Operação", dados["licenca"]),
             ("Validade", dados["validade"]),
             ("Órgão expedidor", dados["orgao"])],
        ]

        historia = [Paragraph(f"PGRS — {filial} · {ano}", titulo)]

        for bloco in blocos:
            linhas = [
                [Paragraph(r, rotulo) for r, _ in bloco],
                [Paragraph(v or "&nbsp;", valor) for _, v in bloco],
            ]
            largura_bloco = util / len(bloco)
            tabela = Table(linhas, colWidths=[largura_bloco] * len(bloco))
            tabela.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, _cores_pdf.HexColor("#9AA8A0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("BACKGROUND", (0, 0), (-1, 0), _cores_pdf.HexColor("#EDF3EE")),
            ]))
            historia.append(tabela)

        historia.append(Spacer(1, 6 * mm))

        corpo = [[Paragraph(r, cabeca) for _, r, _ in COLUNAS_PDF]]
        for posicao, (_, linha) in enumerate(df.iterrows(), start=1):
            visual = []
            for coluna, _, _ in COLUNAS_PDF:
                if coluna == "ITEM":
                    # a numeração é a posição na tabela, não campo digitado:
                    # no documento original ela já tinha saído de ordem
                    bruto = str(posicao)
                elif coluna == COL_MEDIA:
                    numero = para_float(linha.get(coluna), None)
                    bruto = fmt_num(numero) if numero is not None else "—"
                else:
                    bruto = texto_celula(linha.get(coluna))
                visual.append(Paragraph(bruto or "&nbsp;", celula))
            corpo.append(visual)

        larguras = [util * peso for _, _, peso in COLUNAS_PDF]
        tabela = Table(corpo, colWidths=larguras, repeatRows=1)
        tabela.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, _cores_pdf.HexColor("#9AA8A0")),
            ("BACKGROUND", (0, 0), (-1, 0), _cores_pdf.HexColor("#1F7A3D")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [_cores_pdf.white, _cores_pdf.HexColor("#F4F8F5")]),
        ]))
        historia.append(tabela)

        rodape = ParagraphStyle("f", fontName="Helvetica-Oblique", fontSize=6.5,
                                textColor=_cores_pdf.HexColor("#6B7A70"))
        historia.append(Spacer(1, 4 * mm))
        historia.append(Paragraph(
            f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} por "
            f"{usuario_email_logado}. Médias anuais calculadas a partir dos "
            f"lançamentos mensais de {ano} (soma ÷ 12).",
            rodape,
        ))

        doc.build(historia)
        return buffer.getvalue(), None
    except Exception as erro:
        return None, str(erro)


def barra_paginas_consumos() -> str:
    """Navegação da tela de Consumos, na lateral esquerda."""
    st.session_state.setdefault("con_pagina", "lancamento")

    with st.sidebar:
        st.markdown('<p class="dv-sidebar-titulo">Páginas</p>', unsafe_allow_html=True)
        for chave, nome in PAGINAS_CONSUMOS.items():
            ativa = st.session_state["con_pagina"] == chave
            st.button(
                nome,
                key=f"con_pg_{chave}",
                use_container_width=True,
                type="primary" if ativa else "secondary",
                on_click=lambda c=chave: st.session_state.__setitem__("con_pagina", c),
            )

    return st.session_state["con_pagina"]


def filtros_pgrs():
    """Filial e ano do documento. Devolve (filial, ano)."""
    esq, dir_, _ = st.columns([2, 1, 2])
    with esq:
        entrada_filial("pgrs_filial")
    with dir_:
        anos = anos_pgrs()
        # o ano seguinte existe na lista (o PGRS é montado antes do ano
        # fechar) mas não pode nascer escolhido: o padrão é o ano corrente
        st.selectbox("ANO", anos, index=anos.index(date.today().year), key="pgrs_ano")
    return txt("pgrs_filial"), st.session_state.get("pgrs_ano", date.today().year)


CAMPOS_PGRS = (
    "pgrs_residuo", "pgrs_residuo_novo", "pgrs_ibama", "pgrs_classe",
    "pgrs_unidade", "pgrs_frequencia",
) + tuple(f"pgrs_{c}" for c in COLUNAS_ABERTAS_PGRS) + tuple(
    f"pgrs_{c}_novo" for c in COLUNAS_ABERTAS_PGRS
)


def nome_residuo() -> str:
    escolhido = txt("pgrs_residuo")
    return txt("pgrs_residuo_novo") if escolhido == CONTROLE_OUTRO else escolhido


def salvar_pgrs(filial: str, ano: int) -> None:
    residuo = nome_residuo()
    if not residuo:
        st.session_state["msg_pgrs"] = ("warning", "Informe o RESÍDUO.")
        return

    dados = {
        "FILIAL": filial,
        "ANO": int(ano),
        "RESIDUO": residuo,
        COL_IBAMA: txt("pgrs_ibama"),
        "CLASSE": txt("pgrs_classe"),
        COL_UNIDADE: txt("pgrs_unidade"),
        "FREQUENCIA": txt("pgrs_frequencia"),
        "USUARIO": usuario_email_logado,
    }
    for coluna in COLUNAS_ABERTAS_PGRS:
        dados[coluna] = valor_aberto(f"pgrs_{coluna}")

    # A média NÃO é gravada: sai sempre de SUSTENTABILIDADE_CONSUMO, na
    # hora de montar o documento. Os resíduos que ainda não têm coluna lá
    # (lona de freio, lâmpadas, eletrônicos, baterias, pneu, borra de
    # tinta) aparecem sem média até essas colunas existirem — melhor em
    # branco do que um número digitado que ninguém sabe de onde veio.
    concluir("msg_pgrs", "pgrs", dados, CAMPOS_PGRS)


def form_pgrs(filial: str, ano: int) -> None:
    st.caption(f"Lançando em **{filial}** · **{ano}** — o cabeçalho vem dos filtros acima.")

    c1, c2, c3 = st.columns(3)
    with c1:
        escolha = st.selectbox(
            "RESÍDUO",
            opcoes_residuo() + [CONTROLE_OUTRO],
            key="pgrs_residuo",
            on_change=preenche_pelo_residuo,
            help="Escolher o resíduo preenche código IBAMA, classe e unidade",
        )
        if escolha == CONTROLE_OUTRO:
            st.text_input("Qual resíduo?", key="pgrs_residuo_novo",
                          placeholder="nome do resíduo",
                          on_change=preenche_pelo_residuo)

    # primeira abertura da tela: o on_change ainda não disparou
    if "pgrs_ibama" not in st.session_state:
        preenche_pelo_residuo()

    # código, classe e unidade são fixos por resíduo, mas seguem editáveis:
    # resíduo novo não está no catálogo e precisa ser digitado uma vez
    with c2:
        st.text_input("CÓDIGO IBAMA", key="pgrs_ibama")
        st.text_input("CLASSE", key="pgrs_classe")
    with c3:
        st.text_input("UNIDADE", key="pgrs_unidade")
        st.selectbox("FREQUÊNCIA", FREQUENCIAS_PGRS, key="pgrs_frequencia")

    st.markdown("**Manejo**")
    c1, c2, c3 = st.columns(3)
    abertas = list(COLUNAS_ABERTAS_PGRS)
    for i, coluna in enumerate(abertas):
        with [c1, c2, c3][i % 3]:
            entrada_aberta(coluna, f"pgrs_{coluna}")

    st.markdown("**Média anual**")
    residuo = nome_residuo()
    calculada = media_anual_calculada(residuo, codigo_da_filial(filial), ano)
    if calculada is None:
        st.warning(
            f"**{residuo or 'Este resíduo'}** ainda não tem coluna em "
            "Consumos e Serviços, então não há de onde tirar a média. "
            "Ela aparece em branco no documento até a coluna existir."
        )
    else:
        st.info(
            f"Calculada de Consumos e Serviços: **{fmt_num(calculada)}** "
            f"{txt('pgrs_unidade').lower()} — soma de {ano} dividida por 12. "
            "Não é digitada: sai sempre do lançamento mensal."
        )

    st.button("💾 Salvar resíduo", key="btn_salvar_pgrs", type="primary",
              on_click=salvar_pgrs, args=(filial, ano))
    render_msg("msg_pgrs")


def pagina_pgrs() -> None:
    st.markdown("### PGRS — Plano de Gerenciamento de Resíduos Sólidos")
    st.caption(
        "Cadastro anual por filial. Cada linha é um resíduo: código IBAMA, "
        "classe, acondicionamento, destinação e a média anual."
    )

    filial, ano = filtros_pgrs()
    if not filial:
        st.info("Escolha a filial para ver o PGRS.")
        return

    # O recorte é pelo COD_FILIAL da filial escolhida, não pelo nome: o
    # nome tem 98 grafias nas bases antigas, e comparar texto exato é o
    # defeito que o código veio resolver. O filtro de permissão continua
    # valendo por cima — um usuário de filial não alcança outra nem
    # escolhendo, porque a lista dele só tem as dele.
    codigo = codigo_da_filial(filial)
    if not codigo:
        st.warning(
            f"**{filial}** não tem {COL_COD_FILIAL} no cadastro de usuários — "
            "sem o código não há como recortar o documento."
        )
        return

    st.divider()
    aba_doc, aba_novo, aba_editar = st.tabs(
        ["📄 Documento", "➕ Novo resíduo", "✏️ Editar / Excluir"]
    )
    with aba_doc:
        documento_pgrs(filial, ano, codigo)
    with aba_novo:
        form_pgrs(filial, ano)
    with aba_editar:
        painel_edicao("pgrs")


def documento_pgrs(filial: str, ano: int, codigo: str) -> None:
    try:
        cliente = conectar_supabase()
        consulta = (
            cliente.table(TABELA_PGRS)
            .select("*")
            .eq("ANO", int(ano))
            .eq(COL_COD_FILIAL, codigo)
        )
        if not PERFIL["admin"]:
            consulta = consulta.in_(COL_COD_FILIAL, PERFIL["codigos"])
        linhas = consulta.limit(LIMITE_REGISTROS).execute().data or []
    except Exception as erro:
        # A tabela ainda está sendo montada no Supabase: a tela avisa o que
        # falta em vez de estourar um traceback de PostgREST na cara.
        st.warning(
            f"A tabela **{TABELA_PGRS}** ainda não respondeu. Enquanto ela "
            "não existir, esta página fica só com os filtros."
        )
        st.caption(f"Detalhe técnico: {erro}")
        return

    df = pd.DataFrame(linhas)
    if df.empty:
        st.info(f"Nenhum resíduo cadastrado em {filial} para {ano}.")
        return

    df = com_media_anual(df, codigo, ano)
    st.dataframe(limpa_ordem_pgrs(df), hide_index=True, use_container_width=True)

    calculados = int(df["ORIGEM DA MEDIA"].eq("Consumos e Serviços").sum())
    st.caption(
        f"{len(df)} resíduo(s) em {filial} · {ano}. "
        f"{calculados} com média vinda de Consumos e Serviços "
        f"(soma do ano ÷ 12). Os outros {len(df) - calculados} ficam em "
        "branco enquanto não tiverem coluna lá."
    )

    st.divider()
    form_cabecalho_pgrs(filial, codigo)

    conteudo, erro = pdf_pgrs(filial, codigo, ano, df)
    esq, dir_ = st.columns([1, 3])
    if conteudo is not None:
        marca = datetime.now().strftime("%Y%m%d_%H%M")
        with esq:
            st.download_button(
                "📄 Extrair PDF",
                data=conteudo,
                file_name=f"PGRS_{codigo}_{ano}_{marca}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
        with dir_:
            st.caption(
                "O PDF sai com o cabeçalho acima e os resíduos desta filial "
                "neste ano. É ele o registro do que foi entregue — o banco "
                "continua vivo e recalcula a média a cada consulta."
            )
    else:
        with esq:
            st.download_button(
                "⬇️ Extrair CSV",
                data=limpa_ordem_pgrs(df).to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"PGRS_{codigo}_{ano}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dir_:
            st.warning(
                "PDF indisponível: falta o pacote **reportlab** no "
                f"requirements.txt. Enquanto isso sai o CSV. ({erro})"
            )


def com_media_anual(df: pd.DataFrame, codigo: str, ano: int) -> pd.DataFrame:
    """Preenche a média calculada por cima da digitada, quando existe.

    A coluna de origem fica visível de propósito: sem ela ninguém sabe se
    aquele número veio do lançamento mensal ou da mão de alguém.
    """
    saida = df.copy()
    medias, origens = [], []
    for _, linha in saida.iterrows():
        calculada = media_anual_calculada(linha.get("RESIDUO"), codigo, ano)
        medias.append(calculada)
        origens.append("Consumos e Serviços" if calculada is not None
                       else "sem coluna em Consumos")
    saida[COL_MEDIA] = medias
    saida["ORIGEM DA MEDIA"] = origens
    return saida


def limpa_ordem_pgrs(df: pd.DataFrame) -> pd.DataFrame:
    """id e as colunas de controle saem; o resto mantém a ordem da tabela."""
    fora = ("id", COL_COD_FILIAL, "DATA_CRIACAO", "USUARIO")
    return df[[c for c in df.columns if c not in fora]]


def tela_consumos() -> None:
    cabecalho_tela("consumos")

    if barra_paginas_consumos() == "pgrs":
        pagina_pgrs()
        return

    aba_novo, aba_editar = st.tabs(["➕ Novo lançamento", "✏️ Editar / Excluir"])
    with aba_novo:
        form_consumos()
    with aba_editar:
        painel_edicao("consumos")


def tela_licencas() -> None:
    cabecalho_tela("licencas")
    aba_novo, aba_editar = st.tabs(["➕ Novo lançamento", "✏️ Editar / Excluir"])
    with aba_novo:
        form_licencas("licencas")
    with aba_editar:
        painel_edicao("licencas")


def tela_ambiental() -> None:
    cabecalho_tela("ambiental")
    aba_novo, aba_editar = st.tabs(["➕ Novo lançamento", "✏️ Editar / Excluir"])
    with aba_novo:
        form_licencas("ambiental")
    with aba_editar:
        painel_edicao("ambiental")


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
    "ambiental": "Controles Ambientais",
    "custos": "Custos e Orçamentos",
    "reciclaveis": "Recicláveis",
}

# Colunas oferecidas como filtro em cada página, na ordem em que aparecem.
# "multi" = multiselect com os valores existentes; "mes" = multiselect que
# mostra nome do mês mas filtra pelo valor gravado (int ou texto).
FILTROS_RELATORIO = {
    "consumos": [("FILIAL", "multi"), ("ANO", "multi"), ("MES", "mes")],
    # CATEGORIA saiu dos filtros: a página já é o recorte por categoria,
    # e um multiselect com um valor só seria ruído
    "licencas": [("FILIAL", "multi"), ("STATUS", "multi")],
    "ambiental": [("FILIAL", "multi"), ("STATUS", "multi")],
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
    "ambiental": (
        "FILIAL",
        "LICENCA",
        "STATUS",
        COL_DT_VENCIMENTO,
        COL_DIAS,
    ),
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


def fmt_curto(valor: float) -> str:
    """Valor encurtado para caber como rótulo dentro do gráfico.

    12.345 vira '12,3 mil'. Rótulo de ponto disputa espaço com o vizinho:
    o valor por extenso só cabe quando há poucos meses na série.
    """
    if abs(valor) >= 1_000_000:
        texto = f"{valor / 1_000_000:,.1f}".replace(".", ",")
        return f"R$ {texto} mi"
    if abs(valor) >= 1_000:
        texto = f"{valor / 1_000:,.1f}".replace(".", ",")
        return f"R$ {texto} mil"
    return f"R$ {valor:,.0f}".replace(",", ".")


def variacao_mes_anterior(serie: pd.DataFrame, coluna: str) -> pd.DataFrame:
    """Acrescenta VARIACAO: o mesmo mês contra o ano anterior, em %.

    Fica nulo quando não há o mesmo mês no ano passado, ou quando o ano
    passado fechou em zero — dividir por zero daria infinito, e "aumento de
    ∞%" não informa nada.
    """
    saida = serie.copy()
    anterior = {
        (int(a) + 1, int(m)): v
        for a, m, v in zip(saida["ANO_N"], saida["MES_N"], saida[coluna])
    }
    variacoes = []
    for ano, mes, valor in zip(saida["ANO_N"], saida["MES_N"], saida[coluna]):
        base = anterior.get((int(ano), int(mes)))
        variacoes.append(
            (valor - base) / base * 100 if base else None
        )
    saida["VARIACAO"] = variacoes
    return saida


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
# (coluna, rótulo, unidade). A unidade não está no nome da coluna no
# Supabase — os nomes ficaram como nasceram, para não quebrar quem lê a
# tabela por fora. Então ela mora aqui, e é ela que decide o que pode ser
# somado com o quê: kg com kg, nunca kg com kWh.
# (coluna da medição, rótulo, unidade, coluna do valor em R$ ou None).
SERVICOS_CONSUMO = [
    (COL_SOLIDOS, "Sólidos contaminados", "kg", None),
    (COL_OLEO, "Óleo lubrificante", "L", None),
    ("AGUA", "Água", "m³", COL_AGUA_VALOR),
    (COL_ESGOTO, "Esgoto", "m³", COL_ESGOTO_VALOR),
    ("ENERGIA", "Energia", "kWh", COL_ENERGIA_VALOR),
    ("COMUM", "Comum", "kg", None),
    ("MADEIRA", "Madeira", "kg", None),
    ("RECICLAVEIS", "Recicláveis", "kg", None),
    ("CO2", "CO²", "t", None),
]

# Duas famílias somam entre si, e só elas: os resíduos, todos em kg, dão o
# total destinado; as utilidades, todas em R$, dão a conta do período.
RESIDUOS_KG = [c for c, _, u, _ in SERVICOS_CONSUMO if u == "kg"]
UTILIDADES_RS = [v for _, _, _, v in SERVICOS_CONSUMO if v]
TOTAL_RESIDUOS = "Resíduos sólidos (soma)"
TOTAL_UTILIDADES = "Utilidades (soma)"

UNIDADE_DO_SERVICO = {c: u for c, _, u, _ in SERVICOS_CONSUMO}


def fmt_unidade(valor: float, unidade: str) -> str:
    """Número em pt-BR com a unidade colada. Nunca com R$."""
    return f"{fmt_num(valor)} {unidade}"


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
    "ambiental": "Total de controles",
    "reciclaveis": "Lançamentos",
    "custos": "Lançamentos",
}

CARTOES_PAGINA = {
    # a coluna pode ser uma lista: soma horizontal dos serviços
    # O cartão que existia aqui somava as 8 colunas e escrevia R$ no
    # resultado — kg + litro + m³ + kWh + tonelada num número só. Saía
    # "R$ 9.951.353,33", que não era dinheiro nem era nada. No lugar,
    # três cartões que só somam o que é somável.
    "consumos": [
        ("Resíduos sólidos", RESIDUOS_KG, "kg", "verde", None),
        ("Utilidades pagas", UTILIDADES_RS, "brl", "laranja", None),
        ("Água", "AGUA", "m3", "neutro", None),
        ("Energia", "ENERGIA", "kwh", "neutro", None),
    ],
    # formato "cont" conta linhas em vez de somar uma coluna
    "licencas": [
        ("Vencidas", None, "cont", "vermelho", ("STATUS", "VENCIDO")),
        ("Renovar", None, "cont", "laranja", ("STATUS", "RENOVAR")),
        ("No prazo", None, "cont", "verde", ("STATUS", "NO PRAZO")),
    ],
    "ambiental": [
        ("Vencidos", None, "cont", "vermelho", ("STATUS", "VENCIDO")),
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


UNIDADES_CARTAO = {"kg": "kg", "m3": "m³", "kwh": "kWh", "t": "t", "L": "L"}


def formata_valor(valor: float, formato: str) -> str:
    if formato == "brl":
        return fmt_brl(valor)
    if formato in UNIDADES_CARTAO:
        return fmt_unidade(valor, UNIDADES_CARTAO[formato])
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
         "todos os status" if pagina in CATEGORIA_DA_TELA else "no filtro atual")
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


def seta_variacao(pct) -> str:
    """'▲ 12,3%' / '▼ 8,0%'. Receita subindo é bom, então ▲ é positivo.

    O teste de None não basta: ao virar coluna do pandas, o None da variação
    sem par no ano anterior se converte em NaN, que passa por `is not None`
    e imprimiria '▼ nan%'.
    """
    if pct is None or pd.isna(pct):
        return ""
    seta = "▲" if pct >= 0 else "▼"
    return f"{seta} {abs(pct):,.1f}%".replace(".", ",")


def sinal_valor(diferenca: float, formata=None) -> str:
    formata = formata or fmt_brl
    return ("+" if diferenca >= 0 else "−") + formata(abs(diferenca))


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


def comparativo_anual(base: pd.DataFrame, coluna: str, subir_e_bom: bool = True,
                      formata=None):
    """Cartão de variação ano a ano. Devolve (cartão, faixa) ou (None, None).

    subir_e_bom=False inverte a cor: gasto subindo é resultado ruim.
    formata troca o R$ por outra unidade — consumo é medido em kg, m³ e kWh,
    e o percentual seria o mesmo, mas o valor absoluto na nota sairia com
    cifrão em cima de quilo.
    """
    formata = formata or fmt_brl
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
            f"{sinal_valor(diferenca, formata)} · {faixa}: "
            f"{formata(total_atual)} contra {formata(total_anterior)}"
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

    st.markdown("**Receita por mês** — uma linha por ano")
    # Uma linha por ano, e não uma linha corrida no tempo: são 5 anos de
    # lançamento, e a série contínua ficava com dezenas de pontos espremidos.
    # Empilhando os anos sobre os mesmos 12 meses, a distância vertical entre
    # as linhas JÁ É a comparação com o ano anterior.
    mensal = (
        base.groupby(["ANO_N", "MES_N"], as_index=False)["TOTAL_N"]
        .sum()
        .sort_values(["ANO_N", "MES_N"])
    )
    mensal = variacao_mes_anterior(mensal, "TOTAL_N")
    mensal["MES_NOME"] = mensal["MES_N"].map(lambda m: MESES[int(m) - 1])
    mensal["ANO"] = mensal["ANO_N"].astype(str)

    # O rótulo sai só no ano mais recente. Com 5 anos na tela, rotular todas
    # as linhas deixaria 60 textos sobrepostos — ilegível, que é o defeito
    # que o gráfico de barras já tinha.
    ano_recente = int(mensal["ANO_N"].max())
    mensal["TEXTO"] = [
        (
            fmt_curto(v)
            + ("<br>" + seta_variacao(d) if pd.notna(d) else "")
            if int(a) == ano_recente
            else ""
        )
        for a, v, d in zip(mensal["ANO_N"], mensal["TOTAL_N"], mensal["VARIACAO"])
    ]

    fig = px.line(
        mensal,
        x="MES_NOME",
        y="TOTAL_N",
        color="ANO",
        markers=True,
        text="TEXTO",
        category_orders={"MES_NOME": MESES},
        custom_data=["VARIACAO"],
    )
    fig.update_traces(
        texttemplate="%{text}",
        textposition="top center",
        cliponaxis=False,
        hovertemplate=(
            "%{x}<br>R$ %{y:,.2f}"
            "<br>vs. mesmo mês do ano anterior: %{customdata[0]:+.1f}%"
            "<extra>%{fullData.name}</extra>"
        ),
    )
    # folga no topo para o rótulo de duas linhas não encostar na borda
    fig.update_yaxes(range=[0, float(mensal["TOTAL_N"].max()) * 1.30])
    st.plotly_chart(estiliza(fig, 420), use_container_width=True)

    comparaveis = int(mensal["VARIACAO"].notna().sum())
    st.caption(
        f"{len(mensal)} mês(es) com lançamento em {mensal['ANO'].nunique()} ano(s). "
        f"O rótulo mostra o valor de {ano_recente} e, abaixo, a variação contra "
        f"o mesmo mês do ano anterior — ▲ subiu, ▼ caiu. "
        f"{comparaveis} mês(es) têm o mesmo mês no ano anterior para comparar; "
        "nos demais a variação fica em branco em vez de virar 100%."
    )


# ------------------------------------------------
# Análise: Consumos e Serviços
# ------------------------------------------------
def analise_consumos(df: pd.DataFrame) -> None:
    base = com_competencia("consumos", df)
    if base.empty:
        st.info("Sem registros com ANO e MÊS válidos para montar a análise.")
        return

    colunas = [(c, r, u, v) for c, r, u, v in SERVICOS_CONSUMO if c in base.columns]
    numericas = [c for c, _, _, _ in colunas]
    numericas += [v for _, _, _, v in colunas if v and v in base.columns]
    for coluna in numericas:
        base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0)

    # ---------- escolha do serviço ----------
    # Aqui havia um multiselect que somava os serviços marcados, herança de
    # quando se acreditava que todas as colunas eram reais. Cada uma tem a
    # sua unidade: somar duas produz um número que não existe. Agora é um
    # serviço por vez — com uma exceção legítima, os resíduos sólidos, que
    # estão todos em kg e cuja soma é justamente o total destinado.
    kg = [(c, r) for c, r, u, _ in colunas if u == "kg"]
    rs = [(v, r) for _, r, _, v in colunas if v and v in base.columns]
    rotulo_residuos = f"{TOTAL_RESIDUOS} (kg)"
    rotulo_utilidades = f"{TOTAL_UTILIDADES} (R$)"

    # Cada opção carrega as colunas que soma e a unidade do resultado. As
    # duas primeiras são as únicas somas legítimas entre serviços: kg com
    # kg, R$ com R$.
    catalogo = {}
    if len(kg) > 1:
        catalogo[rotulo_residuos] = ([c for c, _ in kg], "kg",
                                     " + ".join(r.lower() for _, r in kg))
    if len(rs) > 1:
        catalogo[rotulo_utilidades] = ([c for c, _ in rs], "R$",
                                       " + ".join(r.lower() for _, r in rs))
    for coluna, rotulo, unidade_col, coluna_valor in colunas:
        catalogo[f"{rotulo} ({unidade_col})"] = ([coluna], unidade_col, rotulo.lower())
        if coluna_valor and coluna_valor in base.columns:
            catalogo[f"{rotulo} (R$)"] = ([coluna_valor], "R$", f"{rotulo.lower()} pago")

    escolha = st.selectbox(
        "Serviço",
        list(catalogo),
        key="ind_consumo_servico",
        help="Um de cada vez: unidades diferentes não somam entre si",
    )
    selecionados, unidade, titulo_selecao = catalogo[escolha]

    base["VALOR"] = base[selecionados].sum(axis=1)

    def formata(valor):
        return fmt_brl(valor) if unidade == "R$" else fmt_unidade(valor, unidade)

    # ---------- cartões ----------
    resumo = resumo_anual(base, "VALOR")
    cartoes = []
    if resumo is not None:
        cartoes.append(
            (
                f"{resumo['faixa']}/{resumo['ano']}",
                formata(resumo["total"]),
                "neutro",
                titulo_selecao,
            )
        )
        if resumo["tem_base"]:
            cartoes.append(
                (
                    f"Mesmo período {resumo['ano'] - 1}",
                    formata(resumo["total_anterior"]),
                    "neutro",
                    f"{resumo['faixa']}/{resumo['ano'] - 1}",
                )
            )
        # consumir mais é resultado ruim: a seta inverte
        cartao_ano, _ = comparativo_anual(
            base, "VALOR", subir_e_bom=False, formata=formata
        )
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
                    f"{formata(atual)} · {MESES[mes_ant - 1]}/{ano_ant}: "
                    f"{formata(anterior)}",
                )
            )
        else:
            cartoes.append(
                (
                    f"{MESES[mes_ref - 1]}/{ano_ref}",
                    formata(atual),
                    "neutro",
                    "sem mês anterior para comparar",
                )
            )

    # ---------- preço unitário ----------
    # É o número que só passou a existir agora que medição e conta estão na
    # mesma linha: R$ por m³, R$ por kWh. Só aparece quando o serviço
    # escolhido tem as duas pontas e as duas estão preenchidas — dividir por
    # medição zerada daria infinito, e por medição ausente, mentira.
    par = next(
        (
            (c, v, r, u)
            for c, r, u, v in colunas
            if v and v in base.columns and c in selecionados + [v]
        ),
        None,
    )
    if par is not None and resumo is not None:
        coluna_medida, coluna_valor, nome_servico, unidade_medida = par
        meses = resumo["meses"]
        periodo = base[
            (base["ANO_N"] == resumo["ano"]) & (base["MES_N"].isin(meses))
        ]
        medida = float(periodo[coluna_medida].sum())
        pago = float(periodo[coluna_valor].sum())
        if medida > 0 and pago > 0:
            cartoes.append(
                (
                    f"R$ por {unidade_medida}",
                    fmt_brl(pago / medida),
                    "neutro",
                    f"{nome_servico} · {resumo['faixa']}/{resumo['ano']}",
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
    st.markdown("**Medição por ano e serviço**")
    da_matriz = [c for c, _, _, _ in colunas]
    da_matriz += [v for _, _, _, v in colunas if v and v in base.columns]
    matriz = base.groupby("ANO_N")[da_matriz].sum()
    matriz.index.name = "ANO"

    unidade_da_coluna = {c: u for c, _, u, _ in colunas}
    renomear = {c: f"{r} ({u})" for c, r, u, _ in colunas}
    for _, rotulo, _, coluna_valor in colunas:
        if coluna_valor and coluna_valor in base.columns:
            unidade_da_coluna[coluna_valor] = "R$"
            renomear[coluna_valor] = f"{rotulo} (R$)"
    if len(kg) > 1:
        matriz[TOTAL_RESIDUOS] = matriz[[c for c, _ in kg]].sum(axis=1)
        unidade_da_coluna[TOTAL_RESIDUOS] = "kg"
        renomear[TOTAL_RESIDUOS] = rotulo_residuos
    if len(rs) > 1:
        matriz[TOTAL_UTILIDADES] = matriz[[c for c, _ in rs]].sum(axis=1)
        unidade_da_coluna[TOTAL_UTILIDADES] = "R$"
        renomear[TOTAL_UTILIDADES] = rotulo_utilidades

    exibir = matriz.rename(columns=renomear).sort_index(ascending=False)
    for origem, rotulo in renomear.items():
        u = unidade_da_coluna[origem]
        exibir[rotulo] = exibir[rotulo].map(
            fmt_brl if u == "R$" else (lambda v, u=u: fmt_unidade(v, u))
        )
    st.dataframe(exibir, use_container_width=True)
    st.caption(
        "Não há coluna de total da linha: somar kg com m³ e kWh não produz "
        "número nenhum. As duas somas que existem são as das famílias que "
        "compartilham unidade — resíduos em kg e utilidades em R$. A matriz "
        "ignora o filtro de serviço acima, de propósito: ela é a visão "
        "completa do ano."
    )

    if not TEM_PLOTLY:
        aviso_sem_plotly()
        return

    # ---------- uma linha por ano ----------
    # este é o gráfico que responde às duas comparações de uma vez: a
    # inclinação da linha é o mês contra o anterior, e a distância entre as
    # linhas é o mesmo mês contra o ano passado
    st.divider()
    st.markdown(f"**{escolha} por mês**")
    grafico = serie.copy()
    grafico["MES_NOME"] = grafico["MES_N"].map(lambda m: MESES[int(m) - 1])
    grafico["ANO"] = grafico["ANO_N"].astype(str)

    fig = px.line(
        grafico.sort_values(["ANO_N", "MES_N"]),
        x="MES_NOME", y="VALOR", color="ANO", markers=True,
        category_orders={"MES_NOME": MESES},
    )
    sufixo = "" if unidade == "R$" else " " + unidade
    prefixo = "R$ " if unidade == "R$" else ""
    fig.update_traces(
        hovertemplate="%{x}<br>" + prefixo + "%{y:,.2f}" + sufixo
        + "<extra>%{fullData.name}</extra>"
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
    "ambiental": analise_licencas,   # mesma leitura, base já recortada
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
    # as duas páginas de licenças leem a mesma tabela: sem o sufixo da
    # categoria, os dois arquivos sairiam com o mesmo nome na pasta
    base_arquivo = TABELAS_DB[pagina]
    if pagina in CATEGORIA_DA_TELA:
        base_arquivo += "_" + CATEGORIA_DA_TELA[pagina]
    marca = datetime.now().strftime("%Y%m%d_%H%M")
    conteudo, erro = para_xlsx(filtrado, nome)
    esq, dir_ = st.columns([1, 3])
    if conteudo is not None:
        with esq:
            st.download_button(
                "⬇️ Extrair XLSX",
                data=conteudo,
                file_name=f"{base_arquivo}_{marca}.xlsx",
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
                file_name=f"{base_arquivo}_{marca}.csv",
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

    # a checagem vem ANTES de barra_paginas() e de pagina_relatorio(): assim
    # nenhuma linha é lida do banco para quem não pode ver a tela
    if not pode_ver("indicador"):
        st.error("Acesso restrito — esta tela é exclusiva da equipe do painel.")
        st.caption(
            f"Seu acesso é de lançamento nas filiais: "
            + (", ".join(PERFIL["filiais"]) or "nenhuma")
            + ". Use o botão Voltar para retornar ao menu."
        )
        return

    pagina = barra_paginas()
    pagina_relatorio(pagina)


# ================================================
# ROTEADOR
# ================================================
ROTAS = {
    "menu": tela_menu,
    "consumos": tela_consumos,
    "licencas": tela_licencas,
    "ambiental": tela_ambiental,
    "custos": tela_custos,
    "reciclaveis": tela_reciclaveis,
    "indicador": tela_indicador,
}

# A navegação é por st.button (ir_para), nunca por link: um <a href> faz o
# navegador recarregar a página, o Streamlit abre uma sessão nova, o token
# do Azure em st.session_state se perde e o login é pedido outra vez.
# terceira camada: se o estado da sessão apontar para uma tela restrita
# (sessão antiga, mudança de perfil), o roteador devolve o menu
_tela_atual = st.session_state["tela"]
if not pode_ver(_tela_atual):
    _tela_atual = "menu"
    st.session_state["tela"] = "menu"

ROTAS.get(_tela_atual, tela_menu)()
