import streamlit as st
import pandas as pd
import re
import pdfplumber
import google.generativeai as genai
import altair as alt
import matplotlib.pyplot as plt
import tempfile
import os
from dataclasses import dataclass
from fpdf import FPDF
import time
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="INOVALENIN - Análise v9.0.3",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- UTILS DE FORMATAÇÃO ---
def formatar_moeda(valor):
    """Formata float para BRL (R$ X.XXX,XX)"""
    if not isinstance(valor, (int, float)): return str(valor)
    texto = f"{valor:,.2f}"
    return f"R$ {texto.replace(',', 'X').replace('.', ',').replace('X', '.')}"

def formatar_numero_br(valor):
    """Formata apenas número para gráficos (X.XXX)"""
    texto = f"{valor:,.0f}"
    return texto.replace(',', '.')

# --- SISTEMA DE LOGIN ---
def check_password():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_role'] = ""
        st.session_state['username'] = ""

    if st.session_state['logged_in']: return True

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("## 🔐 Portal do Cliente - INOVALENIN")
        st.info("Acesso exclusivo para análise de balanços.")
        
        usuario = st.text_input("Usuário:", placeholder="Seu usuário")
        senha = st.text_input("Senha:", type="password", placeholder="Sua senha")
        
        if st.button("Acessar Sistema", type="primary"):
            if "credentials" in st.secrets:
                usuarios_db = st.secrets["credentials"]
                if usuario in usuarios_db and usuarios_db[usuario] == senha:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = usuario
                    st.session_state['user_role'] = "admin" if usuario == "admin_lenine" else "cliente"
                    st.toast(f"Bem-vindo, {usuario}!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("🚫 Usuário ou senha incorretos.")
            else:
                st.error("⚠️ Erro de Configuração: Secrets não encontrados.")
    return False

if not check_password(): st.stop()

# --- CSS CUSTOMIZADO (V9.0.3 - CONTRASTE TOTAL & CLEAN UI) ---
def inject_custom_css(dark_mode):
    # Definição de Paletas de Alto Contraste
    if dark_mode:
        bg_color = "#0e1117"
        text_color = "#ffffff"
        card_bg = "#262730"
        border_color = "#41444d"
        metric_label_color = "#FF0000"
        metric_value_color = "#030202"
        input_bg = "#1e1e1e"
    else:
        bg_color = "#ffffff"
        text_color = "#000000" # Preto absoluto para leitura
        card_bg = "#f8f9fa"    # Cinza muito claro
        border_color = "#bdc3c7" # Cinza médio para borda
        metric_label_color = "#333333"
        metric_value_color = "#000000"
        input_bg = "#ffffff"
    
    css = f"""
    <style>
        /* --- 1. REMOÇÃO DE ELEMENTOS (NUCLEAR) --- */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden; display: none !important;}}
        header {{visibility: hidden; display: none !important;}}
        .stDeployButton {{display: none;}}
        [data-testid="stToolbar"] {{visibility: hidden; display: none !important;}}
        div[class^="viewerBadge"] {{display: none !important;}}
        button[title="View fullscreen"] {{display: none !important;}}
        [data-testid="StyledFullScreenButton"] {{display: none !important;}}
        
        /* --- 2. CONTRASTE E TIPOGRAFIA GLOBAL --- */
        .stApp {{
            background-color: {bg_color};
            color: {text_color};
        }}
        
        /* Força cor de texto em todos os níveis */
        p, h1, h2, h3, h4, h5, h6, li, span, label, div[data-testid="stMarkdownContainer"] p {{
            color: {text_color} !important;
        }}
        
        /* Inputs e Widgets - Garante legibilidade */
        .stTextInput input, .stNumberInput input, .stSelectbox div {{
            color: {text_color} !important;
            background-color: {input_bg};
        }}
        
        /* 3. Abas estilo "Chrome" */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 4px;
            border-bottom: 2px solid {border_color};
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 50px;
            white-space: pre-wrap;
            background-color: {bg_color};
            border-radius: 8px 8px 0px 0px;
            border: 1px solid {border_color};
            border-bottom: none;
            padding: 10px 20px;
            color: {text_color};
        }}
        .stTabs [aria-selected="true"] {{
            background-color: {card_bg} !important;
            border: 2px solid {border_color} !important;
            border-bottom: 2px solid {card_bg} !important;
            font-weight: bold;
            color: {metric_value_color} !important;
        }}
        
        /* 4. Cards de Métricas */
        div[data-testid="stMetric"] {{
            background-color: {card_bg} !important;
            border: 1px solid {border_color} !important;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            text-align: center;
        }}
        div[data-testid="stMetricLabel"] p {{
            color: {metric_label_color} !important;
            font-weight: 600 !important;
        }}
        div[data-testid="stMetricValue"] div {{
            color: {metric_value_color} !important;
        }}
        
        /* 5. Alertas (Warning) - Contraste fixo escuro para fundo amarelo */
        div[data-testid="stAlert"] {{
            background-color: #ffeba0; 
        }}
        div[data-testid="stAlert"] * {{
            color: #5c4b00 !important;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ==============================================================================
# LÓGICA DE NEGÓCIO
# ==============================================================================

@dataclass
class BalancoPatrimonial:
    ativo_circulante: float = 0.0
    ativo_nao_circulante: float = 0.0
    passivo_circulante: float = 0.0
    passivo_nao_circulante: float = 0.0
    patrimonio_liquido: float = 0.0
    estoques: float = 0.0
    @property
    def ativo_total(self): return self.ativo_circulante + self.ativo_nao_circulante
    @property
    def passivo_total(self): return self.passivo_circulante + self.passivo_nao_circulante

@dataclass
class DRE:
    receita_bruta: float = 0.0
    deducoes: float = 0.0
    receita_liquida: float = 0.0
    custos: float = 0.0 
    lucro_bruto: float = 0.0
    despesas_operacionais: float = 0.0
    resultado_operacional: float = 0.0
    lucro_liquido: float = 0.0

class AnalistaFinanceiro:
    def __init__(self, bp: BalancoPatrimonial, dre: DRE):
        self.bp = bp
        self.dre = dre

    def calcular_kpis(self):
        pc = self.bp.passivo_circulante if self.bp.passivo_circulante > 0 else 1.0
        passivo_exigivel = pc + self.bp.passivo_nao_circulante
        if passivo_exigivel == 0: passivo_exigivel = 1.0
        at = self.bp.ativo_total if self.bp.ativo_total > 0 else 1.0
        if self.dre.receita_liquida == 0 and self.dre.receita_bruta > 0:
            self.dre.receita_liquida = self.dre.receita_bruta - self.dre.deducoes
        rl = self.dre.receita_liquida if self.dre.receita_liquida > 0 else 1.0
        lb = self.dre.lucro_bruto
        ro = lb - self.dre.despesas_operacionais
        self.dre.resultado_operacional = ro
        gao = 0.0
        if ro > 0: gao = lb / ro
        ind_desp = (self.dre.despesas_operacionais / rl) * 100

        return {
            "Liquidez Corrente": self.bp.ativo_circulante / pc,
            "Liquidez Seca": (self.bp.ativo_circulante - self.bp.estoques) / pc,
            "Liquidez Geral": (self.bp.ativo_circulante + self.bp.ativo_nao_circulante) / passivo_exigivel,
            "Endividamento Geral (%)": (passivo_exigivel / at) * 100,
            "Margem Bruta (%)": (lb / rl) * 100,
            "Margem Operacional (%)": (ro / rl) * 100,
            "Margem Líquida (%)": (self.dre.lucro_liquido / rl) * 100,
            "GAO (Alavancagem)": gao,
            "Índice Desp. Operacionais (%)": ind_desp,
            "EBIT Calculado": ro
        }

    def gerar_score(self, kpis):
        score = 50
        if kpis["Liquidez Corrente"] >= 1.0: score += 15
        if kpis["Endividamento Geral (%)"] < 60: score += 10
        if kpis["Margem Líquida (%)"] > 10: score += 10
        if kpis["Margem Bruta (%)"] > 30: score += 10
        if kpis["Margem Líquida (%)"] < 0: score -= 20
        if kpis["Liquidez Corrente"] < 0.8: score -= 15
        return min(100, max(0, score))

def listar_modelos_disponiveis(api_key):
    try:
        genai.configure(api_key=api_key)
        modelos = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos.append(m.name)
        modelos.sort()
        return modelos
    except:
        return []

def consultar_ia_financeira(api_key, modelo_escolhido, kpis, dados_dre, nome_empresa, cnpj_empresa, periodo_analise, dre_ant=None, kpis_ant=None):
    if not api_key: return "⚠️ Insira a chave API."
    contexto = f"Empresa: {nome_empresa} (CNPJ: {cnpj_empresa})\nPeríodo Analisado: {periodo_analise}"
    bloco_comparativo = ""
    if dre_ant and kpis_ant:
        def calc_var(atual, anterior):
            if anterior == 0: return 0.0
            return ((atual - anterior) / anterior) * 100
        var_rec = calc_var(dados_dre.receita_liquida, dre_ant.receita_liquida)
        var_lucro = calc_var(dados_dre.lucro_liquido, dre_ant.lucro_liquido)
        var_ebit = calc_var(dados_dre.resultado_operacional, dre_ant.resultado_operacional)
        bloco_comparativo = f"""
        DADOS HISTÓRICOS (PERÍODO ANTERIOR) PARA COMPARAÇÃO:
        - Receita Líquida Anterior: R$ {dre_ant.receita_liquida:,.2f} (Variação Atual: {var_rec:+.2f}%)
        - Lucro Líquido Anterior: R$ {dre_ant.lucro_liquido:,.2f} (Variação Atual: {var_lucro:+.2f}%)
        - EBIT Anterior: R$ {dre_ant.resultado_operacional:,.2f} (Variação Atual: {var_ebit:+.2f}%)
        - Margem Líquida Anterior: {kpis_ant['Margem Líquida (%)']:.1f}%
        
        INSTRUÇÃO ADICIONAL:
        - Você DEVE criar uma seção específica comparando os dois períodos.
        """
    
    # PROMPT ATUALIZADO (v9.0.3) - Assinatura Corrigida
    prompt = f"""
    {contexto}
    Atue como um Analista Financeiro da INOVALENIN.
    Sua tarefa é gerar um Relatório Gerencial detalhado.
    DADOS DO PERÍODO ATUAL:
    - Liquidez Corrente: {kpis['Liquidez Corrente']:.2f}
    - Liquidez Geral: {kpis['Liquidez Geral']:.2f}
    - Endividamento Geral: {kpis['Endividamento Geral (%)']:.1f}%
    - Receita Líquida: R$ {dados_dre.receita_liquida:,.2f}
    - Lucro Bruto: R$ {dados_dre.lucro_bruto:,.2f} (Margem: {kpis['Margem Bruta (%)']:.1f}%)
    - Resultado Operacional (EBIT): R$ {dados_dre.resultado_operacional:,.2f} (Margem: {kpis['Margem Operacional (%)']:.1f}%)
    - Lucro Líquido: R$ {dados_dre.lucro_liquido:,.2f} (Margem: {kpis['Margem Líquida (%)']:.1f}%)
    - GAO: {kpis['GAO (Alavancagem)']:.2f}
    {bloco_comparativo}
    ESTRUTURA OBRIGATÓRIA (Markdown):
    # 1. Identificação e Contexto
    [Cite Nome, CNPJ e Período]
    # 2. Análise da Saúde Financeira (Liquidez e Endividamento)
    [Análise focada em solvência]
    # 3. Análise de Performance Operacional (DRE)
    [Análise de margens, custos e lucro]
    # 4. Análise de Evolução (Comparativo)
    [Se houver dados, compare. Senão, analise sustentabilidade.]
    # 5. Conclusão Técnica e Recomendações
    ## 5.1 Plano de Ação Imediato
    ---
    Recomendamos que este relatório seja discutido com a contabilidade da empresa. Acesse www.inovalenin.com.br.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(modelo_escolhido)
        return model.generate_content(prompt).text
    except Exception as e:
        return f"Erro IA: {str(e)}"

# --- PDF HEADER ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'RELATORIO GERENCIAL DE ANALISE FINANCEIRA (DRE + BALANCO)', 0, 1, 'C')
        
        self.set_font('Arial', 'I', 8)
        self.set_text_color(100, 100, 100)
        aviso_header = "Relatorio gerado pela Rede Neural da INOVALENIN (Versao Beta). Todas as informacoes devem ser conferidas."
        self.cell(0, 5, aviso_header, 0, 1, 'C')
        self.set_text_color(0, 0, 0)
        self.ln(5)

    def footer(self):
        self.set_y(-35) 
        self.set_draw_color(180, 180, 180)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)
        
        self.set_font('Arial', 'B', 7)
        self.cell(0, 4, "AVISO LEGAL:", 0, 1, 'L')
        self.set_font('Arial', '', 7)
        disclaimer = "Este relatorio tem finalidade estritamente gerencial e nao deve ser utilizado para substituir demonstracoes contabeis oficiais. O sistema opera atraves de IA e pode apresentar imprecisoes."
        self.multi_cell(0, 3, disclaimer, 0, 'L')
        self.ln(2)
        
        contato = "Acesse www.inovalenin.com.br | Contato: atendimento@inovalenin.com.br"
        self.multi_cell(0, 3, contato, 0, 'C')
        self.ln(1)
        
        self.set_font('Arial', 'B', 7)
        self.cell(0, 3, "Copyright 2025 - INOVALENIN Solucoes em Tecnologias", 0, 0, 'C')

def criar_grafico_temp(dados, labels, titulo, cor_base):
    plt.figure(figsize=(6, 3))
    colors = [cor_base if v >= 0 else 'red' for v in dados]
    bars = plt.bar(labels, dados, color=colors)
    plt.title(titulo, fontsize=10)
    plt.xticks(rotation=15, ha='right', fontsize=8)
    plt.yticks(fontsize=8)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    for bar in bars:
        height = bar.get_height()
        val_fmt = formatar_numero_br(height)
        plt.text(bar.get_x() + bar.get_width()/2., height, val_fmt, ha='center', va='bottom', fontsize=7)
    plt.tight_layout()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    plt.savefig(temp_file.name, dpi=100)
    plt.close()
    return temp_file.name

def gerar_pdf_final(texto_ia, nome, cnpj, periodo, dre: DRE, bp: BalancoPatrimonial):
    pdf = PDFReport()
    pdf.set_auto_page_break(auto=True, margin=40) 
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Cabeçalho da Empresa
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 7, f"EMPRESA: {nome}", 0, 1)
    pdf.cell(0, 7, f"CNPJ: {cnpj}", 0, 1)
    pdf.ln(4)
    pdf.cell(0, 7, f"PERIODO: {periodo}", 0, 1)
    y_line = pdf.get_y()
    pdf.line(10, y_line, 200, y_line)
    pdf.ln(10)
    
    pdf.set_font("Arial", size=10)
    texto_limpo = texto_ia.replace('```markdown', '').replace('```', '')
    texto_limpo = texto_limpo.replace('**', '').replace('##', '').replace('#', '')
    texto_limpo = texto_limpo.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 5, texto_limpo)
    
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "ANEXO: VISUALIZACAO DE DADOS", 0, 1, 'C')
    pdf.ln(5)
    
    valores_dre = [dre.receita_liquida, dre.custos, dre.lucro_bruto, dre.despesas_operacionais, dre.lucro_liquido]
    labels_dre = ['Rec. Liq', 'Custos', 'L. Bruto', 'Despesas', 'L. Liq']
    img_dre = criar_grafico_temp(valores_dre, labels_dre, "Estrutura DRE", "blue")
    pdf.image(img_dre, x=10, y=None, w=100)
    os.unlink(img_dre)
    
    pdf.set_y(pdf.get_y() + 5)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(90, 8, "Dados da DRE", 1, 1, 'C', fill=False)
    pdf.set_font("Arial", size=8)
    dados_tabela_dre = [("Receita Liquida", dre.receita_liquida), ("(-) Custos", dre.custos), ("(=) Lucro Bruto", dre.lucro_bruto), ("(-) Despesas Oper.", dre.despesas_operacionais), ("(=) Lucro Liquido", dre.lucro_liquido)]
    for desc, val in dados_tabela_dre:
        pdf.cell(60, 6, desc, 1)
        pdf.cell(30, 6, formatar_moeda(val), 1, 1, 'R')
    pdf.ln(10)
    
    valores_bp = [bp.ativo_circulante, bp.passivo_circulante, bp.ativo_total, bp.passivo_total]
    labels_bp = ['Ativo Circ.', 'Pass. Circ.', 'Ativo Total', 'Pass. Total']
    img_bp = criar_grafico_temp(valores_bp, labels_bp, "Estrutura Patrimonial", "green")
    pdf.image(img_bp, x=10, y=None, w=100)
    os.unlink(img_bp)
    
    pdf.set_y(pdf.get_y() + 5)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(90, 8, "Dados do Balanco", 1, 1, 'C', fill=False)
    pdf.set_font("Arial", size=8)
    dados_tabela_bp = [("Ativo Circulante", bp.ativo_circulante), ("Passivo Circulante", bp.passivo_circulante), ("Ativo Total", bp.ativo_total), ("Passivo Total", bp.passivo_total)]
    for desc, val in dados_tabela_bp:
        pdf.cell(60, 6, desc, 1)
        pdf.cell(30, 6, formatar_moeda(val), 1, 1, 'R')
    return pdf.output(dest='S').encode('latin-1')

# --- 5. EXTRAÇÃO ROBUSTA ---
def parse_br_currency(valor_str):
    if not valor_str: return 0.0
    if isinstance(valor_str, (int, float)): return float(valor_str)
    limpo = re.sub(r'[a-zA-Z\s]', '', str(valor_str))
    if ',' in limpo and '.' in limpo:
        limpo = limpo.replace('.', '').replace(',', '.')
    elif limpo.count('.') == 1 and ',' not in limpo:
        parts = limpo.split('.')
        if len(parts[-1]) != 2: limpo = limpo.replace('.', '')
    elif ',' in limpo:
         limpo = limpo.replace(',', '.')
    try:
        return float(limpo)
    except:
        return 0.0

def extrair_periodo_inteligente(texto_completo):
    match_periodo = re.search(r"(?:Período|Exercício|Competência)\s*[:\s-]+\s*((?:\d{1,2}[\/\s]+)?\d{4})", texto_completo, re.IGNORECASE)
    if match_periodo:
        data_bruta = match_periodo.group(1).replace(" ", "").replace("/", "")
        if len(data_bruta) >= 6: 
            ano = data_bruta[-4:]
            return f"01/01/{ano} a 31/12/{ano}"
    linhas = texto_completo.split('\n')
    for linha in linhas:
        if any(x in linha.upper() for x in ["JUNTA", "NIRE", "FUNDAÇÃO"]): continue 
        match_data = re.search(r"31/12/(\d{4})", linha)
        if match_data: return f"01/01/{match_data.group(1)} a 31/12/{match_data.group(1)}"
    anos = re.findall(r"\b20[1-3]\d\b", texto_completo) 
    if anos:
        ano_provavel = max([int(a) for a in anos if int(a) <= datetime.now().year + 1])
        return f"01/01/{ano_provavel} a 31/12/{ano_provavel}"
    return ""

def extrair_dados_texto(texto_completo):
    rx_valor = r"([\d\.,]+)\s*[DC]?" 
    txt_bp = texto_completo[:int(len(texto_completo)*0.6)]
    txt_dre = texto_completo[int(len(texto_completo)*0.4):]
    def buscar_valor(labels, texto_alvo, avoid=[]):
        for label in labels:
            pattern = re.compile(f"{label}.*?{rx_valor}", re.IGNORECASE | re.DOTALL)
            match = pattern.search(texto_alvo)
            if match:
                trecho = match.group(0)
                if any(bad.upper() in trecho.upper() for bad in avoid): continue
                val_str = match.group(1)
                if val_str in ['2023', '2024', '2025']: continue
                val = parse_br_currency(val_str)
                if val > 0: return val
        return 0.0
    ac = buscar_valor(["ATIVO CIRCULANTE"], txt_bp, avoid=["TOTAL", "PASSIVO"]) or buscar_valor(["Total do Ativo Circulante"], txt_bp)
    pc = buscar_valor(["PASSIVO CIRCULANTE"], txt_bp, avoid=["TOTAL", "ATIVO"]) or buscar_valor(["Total do Passivo Circulante"], txt_bp)
    est = buscar_valor(["ESTOQUES", "MERCADORIAS", "ESTOQUE FINAL"], txt_bp)
    anc = buscar_valor(["ATIVO NAO CIRCULANTE", "REALIZAVEL A LONGO PRAZO", "PERMANENTE", "IMOBILIZADO"], txt_bp, avoid=["TOTAL"])
    pnc = buscar_valor(["PASSIVO NAO CIRCULANTE", "EXIGIVEL A LONGO PRAZO"], txt_bp, avoid=["TOTAL"])
    at = buscar_valor(["TOTAL DO ATIVO"], txt_bp)
    if at > ac and anc < (at - ac)*0.9: anc = at - ac
    rb = buscar_valor(["RECEITA BRUTA", "RECEITA OPERACIONAL BRUTA"], txt_dre)
    ded = buscar_valor(["DEDUCOES DA RECEITA", "IMPOSTOS SOBRE VENDAS", "SIMPLES NACIONAL"], txt_dre)
    rl = buscar_valor(["RECEITA LIQUIDA"], txt_dre)
    if rl == 0 and rb > 0: rl = rb - ded
    custos = buscar_valor(["CUSTO DAS MERCADORIAS", "CUSTO DOS PRODUTOS", "CUSTO DOS SERVICOS", "CPV", "CMV"], txt_dre)
    lb = buscar_valor(["LUCRO BRUTO", "RESULTADO BRUTO"], txt_dre)
    if lb == 0: lb = rl - custos
    desp_op = buscar_valor(["DESPESAS OPERACIONAIS", "TOTAL DAS DESPESAS"], txt_dre)
    res_op = buscar_valor(["RESULTADO OPERACIONAL", "LUCRO OPERACIONAL"], txt_dre)
    ll = buscar_valor(["LUCRO DO PERIODO", "LUCRO LIQUIDO DO EXERCICIO"], txt_dre)
    if ll == 0:
        prej = buscar_valor(["PREJUIZO DO PERIODO"], txt_dre)
        if prej > 0: ll = -prej
    if ll == 0:
        ll = buscar_valor(["LUCRO DO PERIODO", "LUCRO LIQUIDO DO EXERCICIO"], txt_dre)
        if ll == 0:
            linhas_dre = txt_dre.split('\n')
            for linha in reversed(linhas_dre):
                if "LUCRO" in linha.upper() or "RESULTADO" in linha.upper():
                    m = re.search(rx_valor, linha)
                    if m:
                        ll = parse_br_currency(m.group(1))
                        break
    return {"ac": ac, "anc": anc, "pc": pc, "pnc": pnc, "est": est, "rb": rb, "ded": ded, "rl": rl, "custos": custos, "lb": lb, "desp_op": desp_op, "res_op": res_op, "ll": ll}

def processar_arquivo(uploaded_file):
    if uploaded_file is None: return None, None
    texto_full = ""
    try:
        if uploaded_file.name.endswith('.pdf'):
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages: texto_full += page.extract_text() + "\n"
        elif uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
            texto_full = df.to_string()
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return None, None
    nome = "Empresa Analisada"
    match_nome = re.search(r"(?:Nome|Empresa)\s*[:\n-]+\s*(.{5,60})", texto_full, re.IGNORECASE)
    if match_nome: nome = match_nome.group(1).strip().split('\n')[0]
    match_cnpj = re.search(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", texto_full)
    cnpj = match_cnpj.group(0) if match_cnpj else ""
    periodo = extrair_periodo_inteligente(texto_full)
    v = extrair_dados_texto(texto_full)
    dados = {
        "bp": BalancoPatrimonial(v['ac'], v['anc'], v['pc'], v['pnc'], 0, v['est']),
        "dre": DRE(receita_bruta=v['rb'], deducoes=v['ded'], receita_liquida=v['rl'], custos=v['custos'], lucro_bruto=v['lb'], despesas_operacionais=v['desp_op'], resultado_operacional=v['res_op'], lucro_liquido=v['ll'])
    }
    return dados, (nome, cnpj, periodo)

# --- 6. INTERFACE PRINCIPAL ---
def main():
    if 'uploader_key' not in st.session_state: st.session_state['uploader_key'] = 0
    if 'relatorio_gerado' not in st.session_state: st.session_state['relatorio_gerado'] = ""
    for k in ['id_nome', 'id_cnpj', 'id_periodo']:
        if k not in st.session_state: st.session_state[k] = ""

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Configurações")
        st.info("ℹ️ **Anexar Balanço + DRE (Atual)**")
        uploaded_file = st.file_uploader("Arquivo Principal", type=["pdf", "xlsx", "xls"], key=f"uploader_{st.session_state['uploader_key']}")
        
        # Modo Escuro/Claro Toggle
        dark_mode = st.toggle("🌙 Modo Escuro", value=True)
        inject_custom_css(dark_mode)

        usar_comparacao = st.checkbox("🔄 Comparar anos anteriores?", help="Habilita upload de um segundo balanço.")
        uploaded_file_ant = None
        if usar_comparacao:
            uploaded_file_ant = st.file_uploader("Arquivo Anterior", type=["pdf", "xlsx", "xls"], key=f"uploader_ant_{st.session_state['uploader_key']}")

        st.markdown("---")
        if st.button("🗑️ Limpar / Nova Análise", use_container_width=True):
            st.session_state['uploader_key'] += 1
            st.session_state['relatorio_gerado'] = ""
            for k in ['id_nome', 'id_cnpj', 'id_periodo']: st.session_state[k] = ""
            st.rerun()
        
        # --- SEGURANÇA: Configurações Apenas para ADMIN (v9.0.3) ---
        if st.session_state.get('user_role') == 'admin':
            with st.expander("🔐 Configurações Técnicas (Oculto)"):
                if "GOOGLE_API_KEY" in st.secrets:
                    api_key = st.secrets["GOOGLE_API_KEY"]
                    st.success("API Key Conectada (Secrets)")
                else:
                    api_key = st.text_input("Google API Key", type="password")
                
                opcoes = listar_modelos_disponiveis(api_key) if api_key else []
                modelo = st.selectbox("Modelo IA:", opcoes, index=0) if opcoes else None
        else:
            # Para clientes, definimos valores padrão silenciosamente se existirem em secrets
            api_key = st.secrets.get("GOOGLE_API_KEY", "")
            modelo = "models/gemini-2.0-flash" # Padrão robusto

        # Dados Iniciais
        dados_iniciais, dados_anterior = None, None
        if uploaded_file:
            dados_iniciais, info = processar_arquivo(uploaded_file)
            if dados_iniciais:
                if not st.session_state['id_nome']: st.session_state['id_nome'] = info[0]
                if not st.session_state['id_cnpj']: st.session_state['id_cnpj'] = info[1]
                if not st.session_state['id_periodo']: st.session_state['id_periodo'] = info[2]
        if uploaded_file_ant:
            dados_anterior, _ = processar_arquivo(uploaded_file_ant)

        # Inputs de Identificação
        st.write("🏢 **Identificação**")
        nome_final = st.text_input("Razão Social:", value=st.session_state['id_nome'])
        cnpj_final = st.text_input("CNPJ:", value=st.session_state['id_cnpj'])
        periodo_final = st.text_input("Período Atual:", value=st.session_state['id_periodo'])

    # --- TÍTULO ATUALIZADO (v9.0.3) ---
    st.title("Análise do Balanço e DRE (v 9.0.3)")
    
    if not dados_iniciais:
        st.info("👋 **Pronto!** Envie o PDF ou Excel no menu lateral para iniciar.")
        st.stop()

    st.warning("⚠️ **Aviso de Versão Beta:** Este sistema está em fase de testes e utiliza Inteligência Artificial. As análises geradas devem ser utilizadas com cautela.", icon="⚠️")

    bp = dados_iniciais['bp']
    dre = dados_iniciais['dre']
    kpis_ant, dre_ant = None, None
    if dados_anterior:
        dre_ant = dados_anterior['dre']
        analista_ant = AnalistaFinanceiro(dados_anterior['bp'], dre_ant)
        kpis_ant = analista_ant.calcular_kpis()
        st.toast("Dados anteriores carregados!", icon="📉")

    check_zeros = (dre.receita_bruta == 0 or dre.lucro_liquido == 0 or dre.custos == 0)
    with st.expander("📝 Editar/Corrigir Valores Extraídos", expanded=check_zeros):
        c1, c2, c3 = st.columns(3)
        with c1:
            dre.receita_bruta = st.number_input("Receita Bruta", value=dre.receita_bruta, format="%.2f")
            dre.deducoes = st.number_input("(-) Deduções", value=dre.deducoes, format="%.2f")
            dre.receita_liquida = st.number_input("Receita Líquida", value=(dre.receita_liquida if dre.receita_liquida > 0 else dre.receita_bruta-dre.deducoes), format="%.2f")
        with c2:
            dre.custos = st.number_input("(-) Custos", value=dre.custos, format="%.2f")
            dre.lucro_bruto = st.number_input("Lucro Bruto", value=(dre.lucro_bruto if dre.lucro_bruto != 0 else dre.receita_liquida-dre.custos), format="%.2f")
            dre.despesas_operacionais = st.number_input("(-) Despesas Oper.", value=dre.despesas_operacionais, format="%.2f")
        with c3:
            dre.lucro_liquido = st.number_input("(=) Lucro Líquido", value=dre.lucro_liquido, format="%.2f")
            bp.ativo_circulante = st.number_input("Ativo Circulante", value=bp.ativo_circulante, format="%.2f")
            bp.passivo_circulante = st.number_input("Passivo Circulante", value=bp.passivo_circulante, format="%.2f")
            bp.ativo_nao_circulante = st.number_input("Ativo Não Circ.", value=bp.ativo_nao_circulante, format="%.2f")
            bp.passivo_nao_circulante = st.number_input("Passivo Não Circ.", value=bp.passivo_nao_circulante, format="%.2f")
            bp.estoques = st.number_input("Estoques", value=bp.estoques, format="%.2f")

    analista = AnalistaFinanceiro(bp, dre)
    kpis = analista.calcular_kpis()
    score = analista.gerar_score(kpis)

    st.divider()
    
    # --- ABAS ESTILIZADAS ---
    tab_kpis, tab_graficos = st.tabs(["📊 Indicadores Financeiros", "📈 Visualização Gráfica"])
    
    def get_delta(chave):
        return (kpis[chave] - kpis_ant[chave]) if kpis_ant else None

    with tab_kpis:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Liquidez Corrente", f"{kpis['Liquidez Corrente']:.2f}", delta=get_delta("Liquidez Corrente"))
        c2.metric("Liquidez Seca", f"{kpis['Liquidez Seca']:.2f}", delta=get_delta("Liquidez Seca"))
        c3.metric("Liquidez Geral", f"{kpis['Liquidez Geral']:.2f}", delta=get_delta("Liquidez Geral"))
        c4.metric("Score", f"{score}/100")

        st.markdown("##### Performance & Rentabilidade")
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Margem Bruta", f"{kpis['Margem Bruta (%)']:.1f}%", delta=get_delta("Margem Bruta (%)"))
        d2.metric("Margem Operacional", f"{kpis['Margem Operacional (%)']:.1f}%", delta=get_delta("Margem Operacional (%)"))
        d3.metric("Margem Líquida", f"{kpis['Margem Líquida (%)']:.1f}%", delta=get_delta("Margem Líquida (%)"))
        d4.metric("GAO", f"{kpis['GAO (Alavancagem)']:.2f}", delta=get_delta("GAO (Alavancagem)"))
        d5.metric("Peso Desp. Oper.", f"{kpis['Índice Desp. Operacionais (%)']:.1f}%", delta=get_delta("Índice Desp. Operacionais (%)"), delta_color="inverse")

    with tab_graficos:
        st.subheader("Análise Visual da Empresa")
        col_g1, col_g2 = st.columns(2)
        
        df_dre_vis = pd.DataFrame({
            'Categoria': ['Receita Líquida', 'Custos', 'Lucro Bruto', 'Despesas Op.', 'Lucro Líquido'],
            'Valor': [dre.receita_liquida, dre.custos, dre.lucro_bruto, dre.despesas_operacionais, dre.lucro_liquido],
            'Tipo': ['Positivo', 'Negativo', 'Resultado', 'Negativo', 'Resultado']
        })
        color_scale = alt.Scale(domain=['Positivo', 'Negativo', 'Resultado'], range=['#2E86C1', '#C0392B', '#27AE60'])
        chart_dre = alt.Chart(df_dre_vis).mark_bar().encode(
            x=alt.X('Categoria', sort=None, title=None),
            y=alt.Y('Valor', title='R$'),
            color=alt.Color('Tipo', scale=color_scale, legend=None),
            tooltip=[alt.Tooltip('Categoria'), alt.Tooltip('Valor', format=',.2f')]
        ).properties(title="Estrutura de Resultados (DRE)")
        col_g1.altair_chart(chart_dre, use_container_width=True)
        
        df_bp_vis = pd.DataFrame({
            'Grupo': ['Ativo Circulante', 'Passivo Circulante', 'Ativo Total', 'Passivo Total'],
            'Valor': [bp.ativo_circulante, bp.passivo_circulante, bp.ativo_total, bp.passivo_total]
        })
        chart_bp = alt.Chart(df_bp_vis).mark_bar().encode(
            x=alt.X('Grupo', sort=None, title=None),
            y=alt.Y('Valor', title='R$'),
            color=alt.value("#8E44AD"),
            tooltip=[alt.Tooltip('Grupo'), alt.Tooltip('Valor', format=',.2f')]
        ).properties(title="Liquidez e Estrutura Patrimonial")
        col_g2.altair_chart(chart_bp, use_container_width=True)

    st.divider()
    st.subheader("📝 Relatório de Análise Financeira")
    
    # --- BOTÃO "GERAR RELATÓRIO" ---
    if st.button("**Gerar Relatório**", type="primary", use_container_width=False):
        if not periodo_final:
            st.warning("⚠️ Informe o PERÍODO no menu lateral.")
        elif modelo and api_key:
            with st.spinner(f"Processando análise..."):
                texto_ia = consultar_ia_financeira(api_key, modelo, kpis, dre, nome_final, cnpj_final, periodo_final, dre_ant, kpis_ant)
                st.session_state['relatorio_gerado'] = texto_ia
        else:
            st.error("Erro de API Key.")

    if st.session_state['relatorio_gerado']:
        with st.container(border=True):
            st.markdown(st.session_state['relatorio_gerado'])
        
        pdf_bytes = gerar_pdf_final(st.session_state['relatorio_gerado'], nome_final, cnpj_final, periodo_final, dre, bp)
        st.download_button(label="📥 Baixar PDF Completo", data=pdf_bytes, file_name=f"Analise_{nome_final}.pdf", mime='application/pdf')

if __name__ == "__main__":
    main()