import streamlit as st
import pandas as pd
# import supabase
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
st.set_page_config(page_title="Metas TDV", layout="wide")

# ================================================
# CLONE DO REPOSITÓRIO DE MÓDULOS (MinIO / Supabase)
# ================================================
modulos_dir = Path(__file__).parent / "Modulos"
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

st.title("🎈 My new app")
st.write(
    "Let's start building! For help and inspiration, head over to [docs.streamlit.io](https://docs.streamlit.io/)."
)
