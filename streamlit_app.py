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
# supabase = ConectionSupaBase.conexao()

# Só chega aqui quem já está autenticado e validado acima.
usuario_email_logado = user_email.lower()


# ================================================
# NAVEGAÇÃO ENTRE TELAS
# ================================================
# Cada tela é identificada por uma chave em st.session_state["tela"].
# "menu" é a tela inicial com os botões de acesso.

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


# ------------------------------------------------
# Persistência provisória (ESBOÇO)
# ------------------------------------------------
# Enquanto o Supabase não estiver estruturado, os registros ficam apenas
# em memória na sessão. Ao ligar o CRUD, basta trocar o corpo de
# salvar_registro() pelo insert na tabela correspondente.

def fmt_brl(valor: float) -> str:
    """Formata no padrão pt-BR: 1234.5 -> R$ 1.234,50"""
    texto = f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {texto}"


def salvar_registro(tabela: str, dados: dict) -> None:
    chave = f"dados_{tabela}"
    dados = dict(dados)
    dados["_usuario"] = usuario_email_logado
    st.session_state.setdefault(chave, []).append(dados)


def listar_registros(tabela: str) -> pd.DataFrame:
    return pd.DataFrame(st.session_state.get(f"dados_{tabela}", []))


def mostrar_registros(tabela: str) -> None:
    df = listar_registros(tabela)
    st.markdown("#### Registros lançados nesta sessão")
    if df.empty:
        st.caption("Nenhum registro lançado ainda.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


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
# 1) CONSUMOS E SERVIÇOS
# ================================================
def tela_consumos() -> None:
    cabecalho_tela("consumos")

    with st.form("form_consumos", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            filial = st.text_input("FILIAL")
        with c2:
            data_ref = st.date_input("DATA", value=date.today(), format="DD/MM/YYYY")

        st.markdown("**Volumes / consumos**")
        c1, c2, c3 = st.columns(3)
        with c1:
            solidos = st.number_input("SÓLIDOS CONTAMINADOS", min_value=0.0, step=0.01, format="%.2f")
            energia = st.number_input("ENERGIA", min_value=0.0, step=0.01, format="%.2f")
            reciclaveis = st.number_input("RECICLÁVEIS", min_value=0.0, step=0.01, format="%.2f")
        with c2:
            oleo = st.number_input("ÓLEO LUBRIFICANTE", min_value=0.0, step=0.01, format="%.2f")
            comum = st.number_input("COMUM", min_value=0.0, step=0.01, format="%.2f")
            co2 = st.number_input("CO²", min_value=0.0, step=0.01, format="%.2f")
        with c3:
            agua = st.number_input("ÁGUA", min_value=0.0, step=0.01, format="%.2f")
            madeira = st.number_input("MADEIRA", min_value=0.0, step=0.01, format="%.2f")

        if st.form_submit_button("💾 Salvar"):
            if not filial.strip():
                st.warning("Informe a FILIAL.")
            else:
                salvar_registro(
                    "consumos",
                    {
                        "FILIAL": filial.strip().upper(),
                        "DATA": data_ref,
                        "SOLIDOS_CONTAMINADOS": solidos,
                        "OLEO_LUBRIFICANTE": oleo,
                        "AGUA": agua,
                        "ENERGIA": energia,
                        "COMUM": comum,
                        "MADEIRA": madeira,
                        "RECICLAVEIS": reciclaveis,
                        "CO2": co2,
                    },
                )
                st.success("Registro salvo na sessão (Supabase pendente).")

    mostrar_registros("consumos")


# ================================================
# 2) CONTROLE DE LICENÇAS
# ================================================
CATEGORIAS_LICENCA = ["LICENCA", "AMBIENTAL"]


def tela_licencas() -> None:
    cabecalho_tela("licencas")

    with st.form("form_licencas", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            filial = st.text_input("FILIAL")
            licenca = st.text_input("LICENÇA")
            status = st.text_input("STATUS")
        with c2:
            rota = st.number_input("ROTA", min_value=0, step=1, format="%d")
            dt_vencimento = st.date_input("DT VENCIMENTO", value=date.today(), format="DD/MM/YYYY")
            categoria = st.selectbox("CATEGORIA", CATEGORIAS_LICENCA)
        with c3:
            cnpj = st.text_input("CNPJ")
            dias_pre = st.number_input("DIAS PRÉ VENCIMENTO", min_value=0, step=1, format="%d")

        observacao = st.text_area("OBSERVAÇÃO")

        if st.form_submit_button("💾 Salvar"):
            if not filial.strip():
                st.warning("Informe a FILIAL.")
            else:
                salvar_registro(
                    "licencas",
                    {
                        "FILIAL": filial.strip().upper(),
                        "ROTA": int(rota),
                        "CNPJ": cnpj.strip(),
                        "LICENCA": licenca.strip(),
                        "DT_VENCIMENTO": dt_vencimento,
                        "DIAS_PRE_VENCIMENTO": int(dias_pre),
                        "STATUS": status.strip(),
                        "OBSERVACAO": observacao.strip(),
                        "CATEGORIA": categoria,
                    },
                )
                st.success("Registro salvo na sessão (Supabase pendente).")

    mostrar_registros("licencas")


# ================================================
# 3) CUSTOS E ORÇAMENTOS
# ================================================
def tela_custos() -> None:
    cabecalho_tela("custos")

    with st.form("form_custos", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            fornecedor = st.text_input("FORNECEDOR")
            pedido = st.text_input("PEDIDO")
            valor = st.number_input("VALOR", min_value=0.0, step=0.01, format="%.2f")
        with c2:
            filial = st.text_input("FILIAL")
            migo = st.text_input("MIGO")
            mes = st.number_input(
                "MÊS", min_value=1, max_value=12, value=date.today().month, step=1, format="%d"
            )
        with c3:
            nota_boleta = st.text_input("NOTA/BOLETA")
            ng = st.text_input("NG")
            dt_pagamento = st.date_input("DATA PAGAMENTO", value=date.today(), format="DD/MM/YYYY")

        if st.form_submit_button("💾 Salvar"):
            if not fornecedor.strip():
                st.warning("Informe o FORNECEDOR.")
            else:
                salvar_registro(
                    "custos",
                    {
                        "FORNECEDOR": fornecedor.strip().upper(),
                        "FILIAL": filial.strip().upper(),
                        "NOTA_BOLETA": nota_boleta.strip(),
                        "PEDIDO": pedido.strip(),
                        "MIGO": migo.strip(),
                        "NG": ng.strip(),
                        "VALOR": valor,
                        "MES": int(mes),
                        "DATA_PAGAMENTO": dt_pagamento,
                    },
                )
                st.success("Registro salvo na sessão (Supabase pendente).")

    mostrar_registros("custos")


# ================================================
# 4) RECICLÁVEIS
# ================================================
# Esta tela NÃO usa st.form: dentro de um formulário o Streamlit só
# reexecuta o script no submit, e o TOTAL (PESO x VALOR/KG) precisa
# acompanhar a digitação. Com widgets soltos + key, cada alteração
# dispara um rerun e o TOTAL é recalculado na hora.

CAMPOS_RECICLAVEIS = ("rec_material", "rec_peso", "rec_valor_kg", "rec_pagamento")
OPCOES_PAGAMENTO = ["Pg Recebido", "Aguardando Pagamento"]


def salvar_reciclaveis() -> None:
    """Callback do botão Salvar; roda antes do rerun, então pode limpar os campos."""
    material = str(st.session_state.get("rec_material", "")).strip()
    if not material:
        st.session_state["rec_msg"] = ("warning", "Informe o MATERIAL.")
        return

    peso = float(st.session_state.get("rec_peso", 0.0))
    valor_kg = float(st.session_state.get("rec_valor_kg", 0.0))
    salvar_registro(
        "reciclaveis",
        {
            "DATA": st.session_state.get("rec_data", date.today()),
            "MATERIAL": material.upper(),
            "PESO": peso,
            "VALOR_KG": valor_kg,
            "TOTAL": round(peso * valor_kg, 2),
            "PAGAMENTO": st.session_state.get("rec_pagamento", OPCOES_PAGAMENTO[0]),
        },
    )

    for campo in CAMPOS_RECICLAVEIS:
        st.session_state.pop(campo, None)
    st.session_state["rec_msg"] = ("success", "Registro salvo na sessão (Supabase pendente).")


def tela_reciclaveis() -> None:
    cabecalho_tela("reciclaveis")

    c1, c2, c3 = st.columns(3)
    with c1:
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

    tipo_msg, texto_msg = st.session_state.pop("rec_msg", (None, None))
    if tipo_msg == "success":
        st.success(texto_msg)
    elif tipo_msg == "warning":
        st.warning(texto_msg)

    mostrar_registros("reciclaveis")


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
