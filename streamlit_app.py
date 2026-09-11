import pandas as pd
from hdbcli import dbapi
from pathlib import PureWindowsPath, Path
import numpy as np
from datetime import datetime
import os

DB_ADDRESS = "PRDBWHANA1"
DB_PORT = 36641
DB_USER = "POWERBIUSER"
DB_PASSOWORD = "P0w3RB1F0rBW#26"


def log(msg):
    """Print com timestamp"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def to_hex(valor):
    """Converte RAW/binario do HANA (memoryview/bytes) em string hexadecimal."""
    if valor is None:
        return None
    if isinstance(valor, memoryview):
        valor = valor.tobytes()
    if isinstance(valor, (bytes, bytearray)):
        return valor.hex().upper()
    if isinstance(valor, float) and pd.isna(valor):
        return None
    return str(valor).upper()


def get_connection():
    """
    Tentando conectar no Banco de Dados SAP HANA
    """
    try:
        log("Conectando no banco de dados")
        conn = dbapi.connect(
            address=DB_ADDRESS,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSOWORD,
        )
        log("Conectado com sucesso")
        return conn
    except Exception as e:
        log(f"Erro ao conectar no banco de dados: {e}")
        raise

def extracao_dados():

    sql_query = """
    SELECT
        LTRIM(uf.TOR_ID, '0') AS UNIDADE_FRETE,
        LTRIM(col.ZC_TRQ_ID, '0') AS COLETA,
        of.TOR_ID AS OF,
        of.CREATED_BY AS CREATED_BY,
        placa_of.PLACA_REAL,
        placa_of.QTD_PLACAS_REAIS,
        col.ZC_ACCESS,
        col.ZC_TRQ_DB,
        col.DESCR_TIPO_CARGA AS TIPO_CARGA,
        col.COD_ORG_VENDAS AS FILIAL,
        col.TIPO_COLETA,
        col.HORA_CRIACAO,
        TO_DATE(NULLIF(col.DATA_PROGRAMACAO, '00000000'), 'YYYYMMDD') AS DATA_PROGRAMACAO_COLETA,
        TO_DATE(NULLIF(col.ZC_DINCNF, '00000000'), 'YYYYMMDD') AS DATA_ENTRADA,
        col.COD_MERCADORIA,
        TO_DATE(col.DATA_CRIACAO, 'YYYYMMDD') AS DATA_CRIACAO_COLETA,
        col.OBSERVACAO,
        col.COLETA_PEDIDO,
        col.QUANTIDADE AS VOLUME_COLETA,
        CASE 
            WHEN col.PESO_UNIDADE = 'TO' THEN col.PESO_BRUTO * 1000
            WHEN col.PESO_UNIDADE = 'KG' THEN col.PESO_BRUTO
        END AS PESO,
        CASE 
        WHEN GREATEST(
            CASE WHEN col.COMPRIMENTO < 1 THEN col.COMPRIMENTO * 100 ELSE col.COMPRIMENTO END,
            CASE WHEN col.LARGURA < 1 THEN col.LARGURA * 100 ELSE col.LARGURA END
        ) >= 209 THEN 'L' 
        ELSE NULL 
        END AS MATERIAL_LONGO,
        CASE 
            WHEN LEFT(REPLACE(col.COD_MERCADORIA, 'ONU-', ''), 4) IS NOT NULL
            AND LEFT(REPLACE(col.COD_MERCADORIA, 'ONU-', ''), 4) <> ''
            AND LEFT(REPLACE(col.COD_MERCADORIA, 'ONU-', ''), 4) <> '0000'
            THEN 'S' 
            ELSE 'N' 
        END AS QUIMICO,
        LEFT(REPLACE(col.COD_MERCADORIA, 'ONU-', ''), 4) AS ONU,
        CASE WHEN col.LARGURA < 1 THEN col.LARGURA * 100 ELSE col.LARGURA END AS LARGURA,
        CASE WHEN col.ALTURA < 1 THEN col.ALTURA * 100 ELSE col.ALTURA END AS ALTURA,
        CASE WHEN col.COMPRIMENTO < 1 THEN col.COMPRIMENTO * 100 ELSE col.COMPRIMENTO END AS COMPRIMENTO,
        uf.SRC_LOC_IDTRQ AS PARCEIRO,
        COALESCE(NULLIF(TRIM(bp_z1.CIDADE), ''), origem.CIDADE) AS ORIGEM,
        COALESCE(NULLIF(TRIM(bp_z1.CEP), ''), origem.CEP) AS CEP_ORIGEM,
        COALESCE(NULLIF(TRIM(bp_z1.RUA), ''), origem.RUA)
            || ', ' || COALESCE(NULLIF(TRIM(bp_z1.NUMERO), ''), origem.NUMERO) AS ENDERECO_ORIGEM,
        COALESCE(NULLIF(TRIM(bp_z1.UF), ''), origem.UF) AS UF_ORIGEM,
        COALESCE(NULLIF(TRIM(bp_z1.BAIRRO), ''), origem.BAIRRO) AS BAIRRO_ORIGEM,
        dest.CIDADE AS DESTINO,
        dest.CEP AS CEP_DESTINO,
        dest.UF AS UF_DESTINO,
        COALESCE(bp_z1.CPF_CNPJ, origem.CPF_CNPJ) AS CNPJ_REMETENTE,
        COALESCE(bp_z1.NOME_PARCEIRO, origem.NOME_PARCEIRO) AS RAZAO_SOCIAL_REMETENTE,
        uf.DES_LOC_IDTRQ AS EXPEDIDOR,
        dest.NOME_PARCEIRO AS RAZAO_SOCIAL_DESTINATARIO,
        dest.CPF_CNPJ AS CNPJ_DESTINATARIO,
        bp.NOME_PARCEIRO AS CLIENTE,
        st.LIFECYCLE AS CICLO_DE_VIDA_COLETA,
        LEFT(nfe.DESCRICAO_PRODUTO, 20) AS DESCRICAO_PRODUTO,
        col.DESCR_TPVEIC,
        COALESCE(NULLIF(TRIM(col.CONTRATO_ACORDO), ''), col.CONTRATO_PORTAL) AS CONTRATO,
        ctr.TXTLG AS CONTRATO_DESCRICAO,
        uf.DB_KEY,
        col.ZC_TRQ_DB AS ROOT_KEY_COLETA,
        blk.DB_KEY AS DB_KEY_BLOQUEIO,
        blk.DATA_BLOQUEIO,
        blk.DATA_DESBLOQUEIO,
        blk.BLOCK_RC_TEXT AS MOTIVO_BLOQUEIO,
        CURRENT_TIMESTAMP as ULTIMA_ATUALIZACAO

    FROM "_SYS_BIC"."TDV.TDV_ORACLE/CV_COLETA" col
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_OF_TOR" uf 
        ON col.ZC_TRQ_ID = uf.TRQ_ID
        AND col.ZC_ITM_ID = uf.ITEM_ID
        AND NULLIF(TRIM(uf.TOR_ID), '') IS NOT NULL
        AND (uf.TOR_TYPE LIKE 'ZF%' OR uf.TOR_TYPE LIKE 'ZT%')
        AND uf.TOR_ID != ''
        AND uf.LIFECYCLE != '10'
        AND uf.DES_LOC_IDTRQ IS NOT NULL 
        AND uf.DES_LOC_IDTRQ <> ''
        AND uf.SRC_LOC_IDTRQ IS NOT NULL
        AND uf.SRC_LOC_IDTRQ <> ''
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_NFE_CLIENTES" nfe
        ON LTRIM(uf.TOR_ID, '0') = LTRIM(nfe.UF_ID, '0')
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_BP_GRUPO_ECONOMICO" gp
        ON gp.COD_PARCEIRO_GP = col.PAGADOR_FRETE
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_STATUS_OEF" st
        ON st.TRQ_ID = col.ZC_TRQ_ID
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_BP" bp
        ON bp.COD_PARCEIRO = COALESCE(NULLIF(TRIM(gp.COD_PARCEIRO), ''), col.PAGADOR_FRETE)
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_BP" origem
        ON origem.COD_PARCEIRO = uf.SRC_LOC_IDTRQ
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_COLETA_PARCEIROS" par_z1
        ON LTRIM(par_z1.NUM_OEF, '0') = LTRIM(col.ZC_TRQ_ID, '0')
        AND par_z1.TIPO_PARCEIRO = 'Z1'
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_BP" bp_z1
        ON bp_z1.COD_PARCEIRO = par_z1.COD_PARCEIRO
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_CONTRATOS" ctr
        ON ctr.TM_FAGIDCA = COALESCE(NULLIF(TRIM(col.CONTRATO_ACORDO), ''), col.CONTRATO_PORTAL)
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_BP" dest
        ON dest.COD_PARCEIRO = uf.DES_LOC_IDTRQ
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_OF_TOR" of
    ON col.ZC_TRQ_ID = of.TRQ_ID
    AND of.TOR_TYPE LIKE 'ZOF%'
    LEFT JOIN (
        SELECT
            TOR_ID,
            CASE
                WHEN COUNT(DISTINCT NULLIF(TRIM(PLATENUMBER), '')) = 1
                THEN MAX(NULLIF(TRIM(PLATENUMBER), ''))
                ELSE NULL
            END AS PLACA_REAL,
            COUNT(DISTINCT NULLIF(TRIM(PLATENUMBER), '')) AS QTD_PLACAS_REAIS
        FROM "_SYS_BIC"."TDV.TDV_ORACLE/CV_OF_TOR"
        WHERE TOR_TYPE = 'ZOF1'
          AND ITEM_CAT = 'AVR'
          AND LIFECYCLE != '10'
          AND NULLIF(TRIM(TOR_ID), '') IS NOT NULL
        GROUP BY TOR_ID
    ) placa_of
        ON placa_of.TOR_ID = of.TOR_ID
    LEFT JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_BLOQUEIO_OEF" blk
    ON col.ZC_TRQ_DB = blk.ROOT_KEY

    WHERE 1 = 1
    --AND col.COD_ORG_VENDAS = '0001'
    AND col.INCOTERMS = 'EXW'
    AND col.ZC_TRQ_TP != 'ZOE5'
    AND uf.LIFECYCLE != '10'
    AND nfe.ZNFEXC_MT IS NULL
    AND (of.TOR_ID IS NULL OR of.TOR_TYPE = 'ZOF1')
    AND st.LIFECYCLE != '10'
    
    AND (
            (col.ZC_ITM_ID != '' AND uf.TOR_ID != '')
            OR (col.ZC_TRQ_ID IS NULL AND of.TOR_TYPE LIKE 'ZOF%')
    )
    AND NOT EXISTS (
            SELECT ev_excluir.ITEM_EVENTO
            FROM "_SYS_BIC"."TDV.TDV_ORACLE/CV_OF_EVENTO" ev_excluir
            WHERE LTRIM(ev_excluir.NUM_OF, '0') = LTRIM(uf.TOR_ID, '0')
            AND ev_excluir.COD_EVENTO IN ('ZV_01','ZV_02','ZV_03','ZV_04','ZV_05')
            AND ev_excluir.NUM_OF IS NOT NULL
            AND TRIM(ev_excluir.NUM_OF) <> ''
            AND SUBSTRING(ev_excluir.NUM_OF,1,12) <> '000000000003'
            AND ev_excluir.COD_EVENTO != 'ARRIV_DEST'
            AND LENGTH(TRIM(ev_excluir.DATA_EVENTO)) = 8
            AND TO_INTEGER(ev_excluir.DATA_EVENTO) BETWEEN 20231212 AND 20301212
            AND ASCII(SUBSTRING(ev_excluir.DATA_EVENTO,7,1)) BETWEEN 48 AND 57
            AND ASCII(SUBSTRING(ev_excluir.DATA_EVENTO,8,1)) BETWEEN 48 AND 57
            AND LENGTH(TRIM(ev_excluir.HORA_EVENTO)) <= 6
            AND TO_INTEGER(LPAD(ev_excluir.HORA_EVENTO,6,'0')) <= 235959
            AND TO_INTEGER(LPAD(ev_excluir.HORA_EVENTO,6,'0')) > 0
            AND TO_INTEGER(ev_excluir.DATA_EVENTO) < 20251001
    )
    AND (
      nfe.ACCESS_ID IS NULL
      OR
      TO_INTEGER(nfe.SEQ) >=
          COALESCE(
              (
                  SELECT MAX(TO_INTEGER(nfe2.SEQ))
                  FROM "_SYS_BIC"."TDV.TDV_ORACLE/CV_NFE_CLIENTES" nfe2
                  JOIN "_SYS_BIC"."TDV.TDV_ORACLE/CV_OF_EVENTO" ev2
                      ON LTRIM(ev2.NUM_OF,'0') = LTRIM(nfe2.UF_ID,'0')
                  WHERE nfe2.ACCESS_ID = nfe.ACCESS_ID
                    AND ev2.COD_EVENTO IN ('ZV_01','ZV_02','ZV_03','ZV_04','ZV_05')
                    AND TO_INTEGER(ev2.DATA_EVENTO) < 20251001
                    AND SUBSTRING(ev2.NUM_OF,1,12) <> '000000000003'
              ),
              -1
          )
    )
    """

    log("Connecting to database...")
    conn = get_connection()
    
  
    log("Executing query and loading data (DATA LOAD START)...")
    df = pd.read_sql(sql_query, conn)

# =======================================LIMPEZA DE BASE ======================================

    filtroLimpezaBase = pd.read_excel(
        r"\\tableau\Central_de_Performance\BI\Cloud\Scripts\Projetos\Indicador_de_CO\Retirar_Coletas_Filtro_Limpeza_Base.xlsx"
    )

    for coluna_chave in ("DB_KEY", "ROOT_KEY_COLETA"):
        df[coluna_chave] = df[coluna_chave].map(to_hex)

    df["FILTRO_LIMPEZA_BASE"] = df["COLETA"].isin(
        filtroLimpezaBase["COLETA"]
    )
    df['TIPO SERVICO'] = "P"
    df['QTDCOLETAS'] = df['COLETA']
    df['CICLO'] = "000"
    df['CHAVE_COLETA'] = df['COLETA'] + "-000-1"
    df['TIPO SERVICO'] = 'P'
    df['CARGA_RISCO'] = 'N'
    df['DESCRICAO_NF'] = ''
    df['DESCRICAO_EMBALAGEM'] = ''
    df['SEQUENCIA'] = ''
    df['COLETA_OCORRENCIADESCRICAO'] = ''
    df['COLETAS_ROTERIZADAS'] = ''

    conditions = [
    # Químico + Carga Risco (1-7)
    (df['LARGURA'] <= 100) & (df['COMPRIMENTO'] <= 120) & (df['ALTURA'] <= 120) & (df['QUIMICO'] == 'S') & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 140) & (df['COMPRIMENTO'] <= 250) & (df['ALTURA'] <= 140) & (df['QUIMICO'] == 'S') & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 180) & (df['COMPRIMENTO'] <= 290) & (df['ALTURA'] <= 180) & (df['QUIMICO'] == 'S') & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 220) & (df['COMPRIMENTO'] <= 380) & (df['ALTURA'] <= 240) & (df['QUIMICO'] == 'S') & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 680) & (df['ALTURA'] <= 240) & (df['QUIMICO'] == 'S') & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 800) & (df['ALTURA'] <= 240) & (df['QUIMICO'] == 'S') & (df['CARGA_RISCO'] == 'SIM'),
    ((df['LARGURA'] > 240) | (df['COMPRIMENTO'] > 800) | (df['ALTURA'] > 240)) & (df['QUIMICO'] == 'S') & (df['CARGA_RISCO'] == 'SIM'),

    # Carga Risco sem Químico (H-N)
    (df['LARGURA'] <= 100) & (df['COMPRIMENTO'] <= 120) & (df['ALTURA'] <= 120) & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 140) & (df['COMPRIMENTO'] <= 250) & (df['ALTURA'] <= 140) & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 180) & (df['COMPRIMENTO'] <= 290) & (df['ALTURA'] <= 180) & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 220) & (df['COMPRIMENTO'] <= 380) & (df['ALTURA'] <= 240) & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 680) & (df['ALTURA'] <= 240) & (df['CARGA_RISCO'] == 'SIM'),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 800) & (df['ALTURA'] <= 240) & (df['CARGA_RISCO'] == 'SIM'),
    ((df['LARGURA'] > 240) | (df['COMPRIMENTO'] > 800) | (df['ALTURA'] > 240)) & (df['CARGA_RISCO'] == 'SIM'),

    # Químico sem Carga Risco (Q-W)
    (df['LARGURA'] <= 100) & (df['COMPRIMENTO'] <= 120) & (df['ALTURA'] <= 120) & (df['QUIMICO'] == 'S'),
    (df['LARGURA'] <= 140) & (df['COMPRIMENTO'] <= 250) & (df['ALTURA'] <= 140) & (df['QUIMICO'] == 'S'),
    (df['LARGURA'] <= 180) & (df['COMPRIMENTO'] <= 290) & (df['ALTURA'] <= 180) & (df['QUIMICO'] == 'S'),
    (df['LARGURA'] <= 220) & (df['COMPRIMENTO'] <= 380) & (df['ALTURA'] <= 240) & (df['QUIMICO'] == 'S'),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 680) & (df['ALTURA'] <= 240) & (df['QUIMICO'] == 'S'),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 800) & (df['ALTURA'] <= 240) & (df['QUIMICO'] == 'S'),
    ((df['LARGURA'] > 240) | (df['COMPRIMENTO'] > 800) | (df['ALTURA'] > 240)) & (df['QUIMICO'] == 'S'),

    # Só dimensão (A-G)
    (df['LARGURA'] <= 100) & (df['COMPRIMENTO'] <= 120) & (df['ALTURA'] <= 120),
    (df['LARGURA'] <= 140) & (df['COMPRIMENTO'] <= 250) & (df['ALTURA'] <= 140),
    (df['LARGURA'] <= 180) & (df['COMPRIMENTO'] <= 290) & (df['ALTURA'] <= 180),
    (df['LARGURA'] <= 220) & (df['COMPRIMENTO'] <= 380) & (df['ALTURA'] <= 240),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 680) & (df['ALTURA'] <= 240),
    (df['LARGURA'] <= 240) & (df['COMPRIMENTO'] <= 800) & (df['ALTURA'] <= 240),
    (df['LARGURA'] > 240) | (df['COMPRIMENTO'] > 800) | (df['ALTURA'] > 240),
    ]

    choices = [
        '1', '2', '3', '4', '5', '6', '7',
        'H', 'I', 'J', 'K', 'L', 'M', 'N',
        'Q', 'R', 'S', 'T', 'U', 'V', 'W',
        'A', 'B', 'C', 'D', 'E', 'F', 'G',
    ]

    df['SELETOR'] = np.select(conditions, choices, default=None)
    df['SELETOR_2'] = df['SELETOR']
    df['VALIDACAO'] = df['SELETOR'] == df['SELETOR_2']
    for coluna_cep in ['CEP_ORIGEM', 'CEP_DESTINO']:
        df[coluna_cep] = (
            df[coluna_cep]
            .astype('string')
            .str.replace(r'\D', '', regex=True)
            .replace('', pd.NA)
            .str.zfill(8)
        )


#===============================MERGE COM TABELA DE BLOQUEIO====================================

    # blqoueio = pd.read_parquet(r'\\tableau\Central_de_Performance\SAP\Calculation_View\CV_BLOQUEIO_OEF.parquet')
    # blqoueio = blqoueio[['ROOT_KEY', 'BLOCK_RC_TEXT', 'DATA_BLOQUEIO', 'DATA_DESBLOQUEIO']].rename(columns={'BLOCK_RC_TEXT': 'MOTIVO_BLOQUEIO'})
    # df = pd.merge(df, blqoueio, how='left', on='ROOT_KEY')

    df['DATA_BLOQUEIO'] = pd.to_datetime(df['DATA_BLOQUEIO'], errors='coerce')
    df['DATA_DESBLOQUEIO'] = pd.to_datetime(df['DATA_DESBLOQUEIO'], errors='coerce')

#  =============================FILTROS DE JANELA=============================================
    aguardando_keywords = [
        "Aguardando Autorização",
        "78- Pendência Fiscal/Física",
        "Aguardando (tratativa)",
        "Bloquear para planejamento de transporte",
        "Coleta aguardando autorização",
        "Aguardando Liberação da Nota Fiscal",
    ]
    interna_keywords = [
        "Aguardando Contrato",
        "Pendência Temporária interna",
    ]

    bloqueio_resolvido = (
        df['DATA_DESBLOQUEIO'].notna() & df['DATA_BLOQUEIO'].notna() &
        (df['DATA_DESBLOQUEIO'] >= df['DATA_BLOQUEIO'])
    )

    tem_keyword_externa = df['MOTIVO_BLOQUEIO'].fillna('').apply(
        lambda x: any(kw in x for kw in aguardando_keywords)
    )
    df['_bloqueio_ativo_ext'] = tem_keyword_externa & ~bloqueio_resolvido
    uf_tem_aguardando_ext = df.groupby('UNIDADE_FRETE')['_bloqueio_ativo_ext'].transform('any')
    df['AGUARDANDO_ACAO_EXTERNA'] = np.where(uf_tem_aguardando_ext, 'Sim', 'Não')
    df = df.drop(columns=['_bloqueio_ativo_ext'])

    tem_keyword_interna = df['MOTIVO_BLOQUEIO'].fillna('').apply(
        lambda x: any(kw in x for kw in interna_keywords)
    )
    df['_bloqueio_ativo_int'] = tem_keyword_interna & ~bloqueio_resolvido
    uf_tem_aguardando_int = df.groupby('UNIDADE_FRETE')['_bloqueio_ativo_int'].transform('any')
    df['AGUARDANDO_ACAO_INTERNA'] = np.where(uf_tem_aguardando_int, 'Sim', 'Não')
    df = df.drop(columns=['_bloqueio_ativo_int'])

    cancelamento_exato = [
        '4- Material Cancelado pelo Cliente',
        '4 - Não Entregue',
        '4 - Material cancelado pelo Cliente',
        'Cancelamento Ocorrência 67',
        '4- Material Cancelado pelo Cliente e 4- Coleta Gerada em Duplicidade',
        'CTe baixado sem vínculo com Vale Frete'
    ]

    bloqueio_valido = (
        df['MOTIVO_BLOQUEIO'].notna() &
        (df['MOTIVO_BLOQUEIO'].str.strip() != '') &
        (df['MOTIVO_BLOQUEIO'].isin(cancelamento_exato) |
        df['MOTIVO_BLOQUEIO'].str.contains('OEF estornada', na=False)
        )
    )
    coletas_canceladas = set(df.loc[bloqueio_valido, 'COLETA'])
    df['CANCELADO'] = df['COLETA'].isin(coletas_canceladas)
    df['ESTORNADO'] = df['DATA_ENTRADA'].notna()

    # ============MERGE PARA PEGAR A DATA DO EVENTO DE IMPRESSAO DA COLETA====================
    impressao = pd.read_parquet(r'\\tableau\Central_de_Performance\SAP\Calculation_View\CV_OF_EVENTO_IMPRESSAO_COLETA.parquet')
    print("Colunas do impressao:", impressao.columns.tolist())
    impressao = impressao.rename(columns={'NUM_OF': 'UNIDADE_FRETE'})
    impressao['UNIDADE_FRETE'] = impressao['UNIDADE_FRETE'].astype(str).str.lstrip('0')
    df = df.merge(impressao[['UNIDADE_FRETE', 'DATA_EVENTO']], how='left', on='UNIDADE_FRETE')
    df = df.rename(columns={'DATA_EVENTO': 'COLETA_DTIMPRESSAO'})
    # =================MERGE NO CEPS DE ROADNET===============================================
    cepsRoadnet = pd.read_excel(r'\\tableau\Central_de_Performance\Arquivos TimeLine\Locais de Atendimento.xlsx')
    cepsRoadnet['CNPJ'] = cepsRoadnet['ID'].str[:14]

    roadnet_max = (
        cepsRoadnet.sort_values('ID', ascending=False)
        .drop_duplicates(subset='CNPJ')[['CNPJ', 'ID', 'Regiões']]
        .rename(columns={'CNPJ': 'CNPJ_REMETENTE', 'ID': 'BUSCA_ROADNET', 'Regiões': 'REGIOES'})
    )
    df = df.merge(roadnet_max, how='left', on='CNPJ_REMETENTE')
    df['CNPJ_ID'] = df['BUSCA_ROADNET'].fillna(df['CNPJ_REMETENTE'] + '-' + df['CEP_ORIGEM'])
    df['ROTA ROADNET'] = np.where(
    df['REGIOES'].isna() | (df['REGIOES'] == ''),
    " || " +  df['CLIENTE'],
    df['REGIOES'] + ' || ' + df['CLIENTE']
    )
    df = df.drop(columns=['BUSCA_ROADNET','REGIOES'])

    df = df.drop_duplicates(subset=['UNIDADE_FRETE', 'MOTIVO_BLOQUEIO'], keep='first')

    baixa = pd.read_parquet(r'\\tableau\Central_de_Performance\SAP\Calculation_View\CV_OF_EVENTO_BAIXA.parquet')
    baixa = baixa.rename(columns={'NUM_OF': 'UNIDADE_FRETE'})
    df = df.merge(baixa[['UNIDADE_FRETE', 'DATA_EVENTO']], how='left', on='UNIDADE_FRETE')


    # ================================MERGE COM PENDENCIA TEMPORARIA===============================

    pendencia = pd.read_parquet(r'\\tableau\Central_de_Performance\BI\Local\Bases_Tratadas\PendenciaTemporaria.parquet')
    pendencia = pendencia.rename(columns={'UF_ID_COL': 'UNIDADE_FRETE'})

    df['PENDENCIA_TEMPORARIA'] = df['UNIDADE_FRETE'].isin(pendencia['UNIDADE_FRETE'])
    # ===============================JANELA OPERACIONAL===============================================
    
    tem_of = df['OF'].notna() & (df['OF'].astype(str).str.strip() != '')
    conditions_janela = [
        df['CANCELADO'],
        df['ESTORNADO'],
        df['PENDENCIA_TEMPORARIA'],
        df['AGUARDANDO_ACAO_EXTERNA'] == 'Sim',
        df['AGUARDANDO_ACAO_INTERNA'] == 'Sim',
        tem_of,
        ~tem_of,
    ]
    choices_janela = [
        'Cancelado',
        'Estornado',
        'Pendencia Temporaria',
        'Aguardando Acao Externa',
        'Aguardando Acao Interna',
        'Diligenciamento',
        'A Coletar',
    ]
    df['JANELA_OPERACIONAL'] = np.select(conditions_janela, choices_janela, default='Sem Janela')

    prioridade_janela = {
        'Cancelado': 1,
        'Estornado': 2,
        'Pendencia Temporaria': 3,
        'Aguardando Acao Externa': 4,
        'Aguardando Acao Interna': 5,
        'Diligenciamento': 6,
        'A Coletar': 7,
        'Sem Janela': 8,
    }
    df['_PRIORIDADE'] = df['JANELA_OPERACIONAL'].map(prioridade_janela)
    janela_por_uf = df.groupby('UNIDADE_FRETE')['_PRIORIDADE'].transform('min')
    prioridade_inversa = {v: k for k, v in prioridade_janela.items()}
    df['JANELA_OPERACIONAL'] = janela_por_uf.map(prioridade_inversa)
    df = df.drop(columns=['_PRIORIDADE'])

    # =============================PESO COM CAPACIDADE MRN===============================================
    depara_roterizacao = {
        'FIORINO':     500,
        '3-4':        3500,
        'TOCO':       7000,
        'TRUCK':     12000,
        'CARRETA':   20000,
        'CARRETA LS':20000,
    }
    df['_CAPACIDADE'] = df['DESCR_TPVEIC'].map(depara_roterizacao)

    condicao_mrn = (
        (df['CONTRATO_DESCRICAO'] == 'MRO-MRN-072024') &
        (df['TIPO_CARGA'] == 'LOTACAO') &
        (df['JANELA_OPERACIONAL'].isin(['A Coletar', 'Diligenciamento']))
    )
    df['PESO'] = np.where(condicao_mrn, df['_CAPACIDADE'], df['PESO'])
    df = df.drop(columns=['_CAPACIDADE'])

     # =============================TIPO_CARGA DEPARA================================================
    depara_tipo_carga = {
        'FRACIONADO': 'FRACIONADO', 'FRACIONADO SEMANAL': 'FRACIONADO',
        'LOTACAO': 'LOTACAO', 'LOTACAO RE': 'LOTACAO',
        'FRACIONADO RE': 'FRACIONADO', 'COLETA': 'FRACIONADO',
        'PROD.QUIMICO': 'FRACIONADO', 'REPARO': 'FRACIONADO',
        'OP.REDONDA': 'OP.REDONDA', 'SUBSTDOCUMENTO': 'FRACIONADO',
        'REDESPACHO': 'FRACIONADO', 'OP.REMOCAO CH': 'OP.REMOCAO CH',
        'DEVOLUCAO': 'FRACIONADO', 'REDEX': 'REDEX',
        'EXPRESSA KM': 'LOTACAO', 'DTA': 'DTA',
        'OUTROS': 'FRACIONADO', 'OP.SIMPLES CH': 'OP.SIMPLES CH',
        'DEDICADO': 'LOTACAO', 'OP.SIMPLES VZ': 'OP.SIMPLES VZ',
        'OP.REAPROVEITAMENTO': 'OP.REAPROVEITAMENTO', 'REENTREGA': 'FRACIONADO',
        'REMOCAO': 'REMOCAO', 'OP. REDONDA TROCA NO': 'OP. REDONDA TROCA NO',
        'NORMAL': 'FRACIONADO', 'MILK RUN': 'LOTACAO',
        'RETIRADA EM ARMAZEM': '', 'SPOT KM': 'LOTACAO',
    }
    df['TIPO_CARGA'] = df['TIPO_CARGA'].map(depara_tipo_carga).fillna(df['TIPO_CARGA'])
    # =============================TIPO_CARGA DEPARA MRN===============================================
    condicao_tipo_mrn = (
        (df['CONTRATO_DESCRICAO'] == 'MRO-MRN-072024') &
        (df['TIPO_CARGA'] == 'LOTACAO')
    )
    df['TIPO_CARGA'] = np.where(condicao_tipo_mrn, 'FRACIONADO', df['TIPO_CARGA'])

    # =============================TIPO_CARGA DEPARA VALE===============================================
    condicao_vale = (
        (df['CLIENTE'] == 'VALE SA') &
        (df['FILIAL'] == '0001') &
        (df['PESO'] < 100) &
        (df['TIPO_COLETA'] == 'Expresso')
    )
    df['TIPO_CARGA'] = np.where(condicao_vale, 'LOTACAO AEREO', df['TIPO_CARGA'])

     # =============================TIPO_CARGA DEPARA VALE===============================================
    condicao_vale = (
        (df['CLIENTE'] == 'VALE SA') &
        (df['FILIAL'] == '0001') &
        (df['PESO'] < 100) &
        (df['TIPO_COLETA'] == 'Expresso')
    )
    df['TIPO_CARGA'] = np.where(condicao_vale, 'LOTACAO AEREO', df['TIPO_CARGA'])
    
    # ==================LOTACAO -> FRACIONADO (CLIENTE + CNPJ REMETENTE + CONTRATO)==================
    cnpj_vale = [
        '17783830000135', '45561404000192', '07175725001050', '07175725002103',
        '50859446000306', '50859446000144', '56389562000123', '08624328000190',
    ]

    cnpj_norm = df['CNPJ_REMETENTE'].astype('string').str.replace(r'\D', '', regex=True).str.zfill(14)

    cond_vale = (
        (df['CLIENTE'] == 'VALE SA')
        & cnpj_norm.isin(cnpj_vale)
        & (df['CONTRATO_DESCRICAO'] == 'MRO-VALE-LOTACAO-SUDESTE-0723')
        & (df['TIPO_CARGA'] == 'LOTACAO')
    )

    cond_albras = (
        (df['CLIENTE'] == 'ALBRAS')
        & (cnpj_norm == '68474485000199')
        & (df['CONTRATO_DESCRICAO'] == 'MRO-20230001-HYDRO ALBRAS')
        & (df['TIPO_CARGA'] == 'LOTACAO')
    )

    df['TIPO_CARGA'] = np.where(cond_vale | cond_albras, 'FRACIONADO', df['TIPO_CARGA'])

    # =============================FILTRO SOMENTE LOTACAO=============================================
    bloqueios = pd.read_parquet(
        r'\\tableau\Central_de_Performance\Arquivos TimeLine\CV_BLOQUEIO_OEF_BACKUP.parquet',
        columns=['ROOT_KEY', 'BLOCK_RC_TEXT', 'DATA_BLOQUEIO', 'DATA_DESBLOQUEIO'],
    )
    bloqueios['ROOT_KEY'] = bloqueios['ROOT_KEY'].map(to_hex)
    bloqueios = bloqueios.rename(columns={'BLOCK_RC_TEXT': 'MOTIVO_BLOQUEIO'})
    bloqueios['DATA_BLOQUEIO'] = pd.to_datetime(bloqueios['DATA_BLOQUEIO'], errors='coerce')
    bloqueios['DATA_DESBLOQUEIO'] = pd.to_datetime(bloqueios['DATA_DESBLOQUEIO'], errors='coerce')
    # mantem apenas o bloqueio mais recente de cada ROOT_KEY para nao multiplicar linhas
    bloqueios = (
        bloqueios.sort_values('DATA_BLOQUEIO')
        .drop_duplicates(subset='ROOT_KEY', keep='last')
    )

    colunas_bloqueio = ['MOTIVO_BLOQUEIO', 'DATA_BLOQUEIO', 'DATA_DESBLOQUEIO']
    df = pd.merge(
        df,
        bloqueios,
        how='left',
        left_on='ROOT_KEY_COLETA',
        right_on='ROOT_KEY',
        suffixes=('', '_BKP'),
    )
    # o backup so completa o que nao veio da CV_BLOQUEIO_OEF no SQL
    for coluna in colunas_bloqueio:
        df[coluna] = df[coluna].fillna(df[f'{coluna}_BKP'])
    df = df.drop(columns=['ROOT_KEY'] + [f'{c}_BKP' for c in colunas_bloqueio])

    # =============================CRIAÇÃO DO PARQUET================================================
    output_path = r'\\tableau\Central_de_Performance\BI\Local\Bases_Tratadas\RoadNet.parquet'
    print("Gerando Parquet do RoadNet...")

    try:
        df.to_parquet(output_path, index=False)
        output_file = Path(output_path)
        if output_file.exists() and output_file.stat().st_size > 0:
            tamanho_mb = round(output_file.stat().st_size / (1024 * 1024), 2)
            print("Parquet salvo com sucesso!")
            print(f"   Caminho : {output_path}")
            print(f"   Tamanho : {tamanho_mb} MB")
            print(f"   Linhas  : {len(df):,} | Colunas: {len(df.columns)}")
        else:
            print(f"AVISO: arquivo não encontrado ou vazio após salvar: {output_path}")

    except PermissionError:
        print(f"ERRO: sem permissão para salvar em: {output_path}")
    except OSError as e:
        print(f"ERRO de sistema ao salvar o parquet: {e}")
    except Exception as e:
        print(f"ERRO inesperado ao salvar o parquet: {e}")

    # gerar_log('Final do Script')
    print("\n=== Concluído ===")

    conn.close()
    log("Connection closed. Process finished.")


if __name__ == "__main__":
    extracao_dados()
