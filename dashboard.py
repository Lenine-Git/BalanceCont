import streamlit as st
import pandas as pd
import re
import pdfplumber
import google.generativeai as genai
from dataclasses import dataclass
from fpdf import FPDF
import time
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="INOVALENIN - Dashboard Financeiro v8.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- SISTEMA DE LOGIN ---
def check_password():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_role'] = ""
        st.session_state['username'] = ""

    if st.session_state['logged_in']:
        return True

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("## 🔐 Portal do Cliente - INOVALENIN")
        st.info("Acesso exclusivo para análise de balanços.")
        
        usuario = st.text_input("Usuário:", placeholder="Seu usuário de acesso")
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
                st.error("⚠️ Erro de Configuração: Base de usuários não encontrada.")
    return False

if not check_password():
    st.stop()

if st.session_state['user_role'] == "admin":
    with st.expander("🛠️ Painel Master"):
        st.write(f"Logado como: **{st.session_state['username']}**")

st.sidebar.title(f"👤 {st.session_state['username']}")
if st.sidebar.button("Sair / Logout"):
    st.session_state['logged_in'] = False
    st.rerun()

# ==============================================================================
# LÓGICA DO DASHBOARD (VERSÃO 8.0 - DRE PROFUNDA)
# ==============================================================================

# --- 2. LÓGICA DE NEGÓCIO ---
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

@dataclass
class DRE:
    receita_bruta: float = 0.0
    deducoes: float = 0.0
    receita_liquida: float = 0.0
    custos: float = 0.0 # CPV / CSP
    lucro_bruto: float = 0.0
    despesas_operacionais: float = 0.0
    resultado_operacional: float = 0.0 # EBIT
    lucro_liquido: float = 0.0

class AnalistaFinanceiro:
    def __init__(self, bp: BalancoPatrimonial, dre: DRE):
        self.bp = bp
        self.dre = dre

    def calcular_kpis(self):
        # --- BALANÇO ---
        pc = self.bp.passivo_circulante if self.bp.passivo_circulante > 0 else 1.0
        passivo_exigivel = pc + self.bp.passivo_nao_circulante
        if passivo_exigivel == 0: passivo_exigivel = 1.0
        at = self.bp.ativo_total if self.bp.ativo_total > 0 else 1.0
        
        # --- DRE INDICADORES ---
        rb = self.dre.receita_bruta if self.dre.receita_bruta > 0 else 1.0
        rl = self.dre.receita_liquida if self.dre.receita_liquida > 0 else 1.0
        lb = self.dre.lucro_bruto
        ro = self.dre.resultado_operacional
        
        # Graus de Alavancagem Operacional (GAO) = Lucro Bruto / Resultado Operacional
        # Cuidado com divisão por zero ou números negativos que distorcem o GAO
        gao = 0.0
        if ro > 0:
            gao = lb / ro

        # Índice de Despesas Operacionais = Desp. Operacionais / Receita Líquida
        ind_desp = (self.dre.despesas_operacionais / rl) * 100

        return {
            # BP Indices
            "Liquidez Corrente": self.bp.ativo_circulante / pc,
            "Liquidez Seca": (self.bp.ativo_circulante - self.bp.estoques) / pc,
            "Liquidez Geral": (self.bp.ativo_circulante + self.bp.ativo_nao_circulante) / passivo_exigivel,
            "Endividamento Geral (%)": (passivo_exigivel / at) * 100,
            
            # DRE Indices (Novos v8.0)
            "Margem Bruta (%)": (lb / rl) * 100,
            "Margem Operacional (%)": (ro / rl) * 100,
            "Margem Líquida (%)": (self.dre.lucro_liquido / rl) * 100,
            "GAO (Alavancagem)": gao,
            "Índice Desp. Operacionais (%)": ind_desp
        }

    def gerar_score(self, kpis):
        score = 50
        # Regras BP
        if kpis["Liquidez Corrente"] >= 1.0: score += 15
        if kpis["Endividamento Geral (%)"] < 60: score += 15
        
        # Regras DRE
        if kpis["Margem Líquida (%)"] > 10: score += 10
        if kpis["Margem Bruta (%)"] > 30: score += 10
        if kpis["Margem Operacional (%)"] > 10: score += 10
        
        # Penalidades
        if kpis["Margem Líquida (%)"] < 0: score -= 20
        if kpis["Liquidez Corrente"] < 0.8: score -= 10
        
        return min(100, max(0, score))

# --- 3. SERVIÇO DE IA ---
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

def consultar_ia_financeira(api_key, modelo_escolhido, kpis, dados_dre, nome_empresa, cnpj_empresa, periodo_analise):
    if not api_key: return "⚠️ Insira a chave API."

    contexto = f"Empresa: {nome_empresa} (CNPJ: {cnpj_empresa})\nPeríodo Analisado: {periodo_analise}"
    
    prompt = f"""
    {contexto}
    Atue como um Analista Financeiro Sênior da INOVALENIN.
    Gere um Relatório Gerencial Detalhado (DRE e Balanço).
    
    DADOS DO BALANÇO:
    - Liquidez Corrente: {kpis['Liquidez Corrente']:.2f}
    - Endividamento Geral: {kpis['Endividamento Geral (%)']:.1f}%
    
    DADOS DA DRE (PERFORMANCE):
    - Receita Bruta: R$ {dados_dre.receita_bruta:,.2f}
    - (-) Deduções: R$ {dados_dre.deducoes:,.2f}
    - (=) Receita Líquida: R$ {dados_dre.receita_liquida:,.2f}
    - (-) Custos (CMV/CPV): R$ {dados_dre.custos:,.2f}
    - (=) Lucro Bruto: R$ {dados_dre.lucro_bruto:,.2f} (Margem: {kpis['Margem Bruta (%)']:.1f}%)
    - (-) Despesas Operacionais: R$ {dados_dre.despesas_operacionais:,.2f}
    - (=) Resultado Operacional: R$ {dados_dre.resultado_operacional:,.2f} (Margem: {kpis['Margem Operacional (%)']:.1f}%)
    - (=) Lucro Líquido: R$ {dados_dre.lucro_liquido:,.2f} (Margem: {kpis['Margem Líquida (%)']:.1f}%)
    - GAO (Alavancagem): {kpis['GAO (Alavancagem)']:.2f}

    ESTRUTURA OBRIGATÓRIA (Markdown):
    
    # 1. Identificação e Contexto
    [Confirme que é uma análise automática da rede neural INOVALENIN. Identifique a empresa e o período]

    # 2. Análise Vertical da DRE (Detalhamento)
    ## 2.1 Eficiência de Custos
    [Analise a proporção de Deduções e Custos sobre a Receita. O Lucro Bruto está saudável?]
    
    ## 2.2 Peso das Despesas Operacionais
    [Analise o impacto das despesas administrativas/comerciais sobre o Lucro Bruto. A empresa é pesada?]

    ## 2.3 Capacidade de Geração de Caixa (EBITDA/Operacional)
    [Comente sobre o Resultado Operacional e a Margem Operacional]

    # 3. Indicadores de Balanço e Solvência
    [Breve análise de Liquidez e Endividamento]

    # 4. Análise de Alavancagem e Retorno
    [Explique o GAO encontrado. A empresa tem alto risco operacional?]

    # 5. Conclusão Técnica e Recomendações
    [Parecer final sintético]
    ## 5.1 Plano de Ação
    [3 ações para melhorar margens ou reduzir despesas]
    
    ---
    Recomendamos que este relatório seja discutido com a contabilidade da empresa para esclarecimentos mais detalhados. Acesse o site da INOVALENIN (www.inovalenin.com.br) para conhecer mais soluções tecnológicas que auxiliarão na gestão da sua empresa.
    """

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(modelo_escolhido)
        return model.generate_content(prompt).text
    except Exception as e:
        return f"Erro IA: {str(e)}"

# --- 4. GERAÇÃO DE PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'RELATORIO DE ANALISE FINANCEIRA (DRE + BP)', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        texto = "Relatorio criado por INOVALENIN Solucoes em Tecnologias - www.inovalenin.com.br - atendimento@inovalenin.com.br"
        self.cell(0, 10, texto, 0, 0, 'C')

def gerar_pdf_final(texto_ia, nome, cnpj, periodo):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 7, f"EMPRESA: {nome}", 0, 1)
    pdf.cell(0, 7, f"CNPJ: {cnpj}", 0, 1)
    pdf.cell(0, 7, f"PERIODO: {periodo}", 0, 1)
    pdf.line(10, 40, 200, 40)
    pdf.ln(10)
    
    pdf.set_font("Arial", size=10)
    texto_limpo = texto_ia.replace('**', '').replace('##', '').replace('#', '')
    texto_limpo = texto_limpo.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 5, texto_limpo)
    
    return pdf.output(dest='S').encode('latin-1')

# --- 5. EXTRAÇÃO ROBUSTA (DRE EXPANDIDA) ---
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
    match_periodo = re.search(r"(?:Período|Exercício|Competência).*?(\d{2}/\d{2,4}\s+a\s+\d{2}/\d{2,4})", texto_completo, re.IGNORECASE)
    if match_periodo: return match_periodo.group(1).strip()
    return ""

def extrair_dados_texto(texto_completo):
    rx_valor = r"([\d\.,]+)\s*[DC]?" 
    
    # Divide texto para evitar confusão Balanço x DRE
    meio = len(texto_completo) // 2
    txt_bp = texto_completo[:int(len(texto_completo)*0.6)]
    txt_dre = texto_completo[int(len(texto_completo)*0.4):]

    def buscar(labels, texto_alvo, avoid=[]):
        for label in labels:
            # Regex que busca na mesma linha ou linhas próximas
            pattern = re.compile(f"{label}.*?{rx_valor}", re.IGNORECASE | re.DOTALL)
            match = pattern.search(texto_alvo)
            if match:
                trecho = match.group(0)
                if any(bad.upper() in trecho.upper() for bad in avoid): continue
                val_str = match.group(1)
                if val_str in ['2023', '2024']: continue
                val = parse_br_currency(val_str)
                if val > 0: return val
        return 0.0

    # --- BALANÇO ---
    ac = buscar(["ATIVO CIRCULANTE"], txt_bp, avoid=["TOTAL", "PASSIVO"]) or buscar(["Total do Ativo Circulante"], txt_bp)
    pc = buscar(["PASSIVO CIRCULANTE"], txt_bp, avoid=["TOTAL", "ATIVO"]) or buscar(["Total do Passivo Circulante"], txt_bp)
    est = buscar(["ESTOQUES", "MERCADORIAS", "ESTOQUE FINAL"], txt_bp)
    anc = buscar(["ATIVO NAO CIRCULANTE", "REALIZAVEL A LONGO PRAZO"], txt_bp, avoid=["TOTAL"])
    pnc = buscar(["PASSIVO NAO CIRCULANTE", "EXIGIVEL A LONGO PRAZO"], txt_bp, avoid=["TOTAL"])
    at = buscar(["TOTAL DO ATIVO"], txt_bp)
    if at > ac and anc < (at - ac)*0.9: anc = at - ac

    # --- DRE DETALHADA (V8.0) ---
    rb = buscar(["RECEITA BRUTA", "RECEITA OPERACIONAL BRUTA"], txt_dre)
    
    # Deduções (Impostos/Devoluções)
    ded = buscar(["DEDUCOES DA RECEITA", "IMPOSTOS SOBRE VENDAS", "SIMPLES NACIONAL", "ICMS SOBRE VENDAS"], txt_dre)
    
    # Receita Liquida (Se não achar, calcula)
    rl = buscar(["RECEITA LIQUIDA"], txt_dre)
    if rl == 0 and rb > 0: rl = rb - ded
    
    # Custos (CMV/CPV/CSP)
    custos = buscar(["CUSTO DAS MERCADORIAS", "CUSTO DOS PRODUTOS", "CUSTO DOS SERVICOS", "CPV", "CMV", "CSP"], txt_dre)
    
    # Lucro Bruto (Se não achar, calcula)
    lb = buscar(["LUCRO BRUTO", "RESULTADO BRUTO"], txt_dre)
    if lb == 0: lb = rl - custos
    
    # Despesas Operacionais (Geralmente é um totalizador ou soma de Adm + Com)
    desp_op = buscar(["DESPESAS OPERACIONAIS", "TOTAL DAS DESPESAS"], txt_dre)
    
    # Resultado Operacional (EBITDA aproximado ou EBIT)
    res_op = buscar(["RESULTADO OPERACIONAL", "LUCRO OPERACIONAL"], txt_dre)
    if res_op == 0: res_op = lb - desp_op
    
    # Lucro Líquido
    ll = buscar(["LUCRO DO PERIODO", "LUCRO LIQUIDO DO EXERCICIO"], txt_dre)
    if ll == 0:
        prej = buscar(["PREJUIZO DO PERIODO"], txt_dre)
        if prej > 0: ll = -prej

    return {
        "ac": ac, "anc": anc, "pc": pc, "pnc": pnc, "est": est, 
        "rb": rb, "ded": ded, "rl": rl, "custos": custos, 
        "lb": lb, "desp_op": desp_op, "res_op": res_op, "ll": ll
    }

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
    
    # Monta objetos ricos (V8.0)
    dados = {
        "bp": BalancoPatrimonial(v['ac'], v['anc'], v['pc'], v['pnc'], 0, v['est']),
        "dre": DRE(
            receita_bruta=v['rb'], 
            deducoes=v['ded'],
            receita_liquida=v['rl'],
            custos=v['custos'],
            lucro_bruto=v['lb'],
            despesas_operacionais=v['desp_op'],
            resultado_operacional=v['res_op'],
            lucro_liquido=v['ll']
        )
    }
    return dados, (nome, cnpj, periodo)

# --- 6. INTERFACE ---
def main():
    st.markdown("""
        <style>
        @media print { .stSidebar {display: none;} }
        .footer {position: fixed; left: 0; bottom: 0; width: 100%; background-color: #f1f1f1; color: #666; text-align: center; padding: 10px; font-size: 12px; z-index: 100;}
        </style>
    """, unsafe_allow_html=True)

    if 'uploader_key' not in st.session_state: st.session_state['uploader_key'] = 0
    if 'relatorio_gerado' not in st.session_state: st.session_state['relatorio_gerado'] = ""
    
    # Estados de Identificação
    for k in ['id_nome', 'id_cnpj', 'id_periodo']:
        if k not in st.session_state: st.session_state[k] = ""

    with st.sidebar:
        st.header("⚙️ Configurações")
        st.info("ℹ️ **Anexar Balanço + DRE**")
        uploaded_file = st.file_uploader("Arquivo (PDF/Excel)", type=["pdf", "xlsx", "xls"], key=f"uploader_{st.session_state['uploader_key']}")
        
        if st.button("🗑️ Limpar", use_container_width=True):
            st.session_state['uploader_key'] += 1
            st.session_state['relatorio_gerado'] = ""
            for k in ['id_nome', 'id_cnpj', 'id_periodo']: st.session_state[k] = ""
            st.rerun()
        
        st.markdown("---")
        dados_iniciais = None
        if uploaded_file:
            dados_iniciais, info = processar_arquivo(uploaded_file)
            if dados_iniciais:
                if not st.session_state['id_nome']: st.session_state['id_nome'] = info[0]
                if not st.session_state['id_cnpj']: st.session_state['id_cnpj'] = info[1]
                if not st.session_state['id_periodo']: st.session_state['id_periodo'] = info[2]
        
        st.write("🏢 **Identificação**")
        nome_final = st.text_input("Razão Social:", value=st.session_state['id_nome'])
        cnpj_final = st.text_input("CNPJ:", value=st.session_state['id_cnpj'])
        periodo_final = st.text_input("Período:", value=st.session_state['id_periodo'])
        
        st.markdown("---")
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
            st.success("🔑 IA Conectada.")
        else:
            api_key = st.text_input("Google API Key", type="password")
        
        opcoes = listar_modelos_disponiveis(api_key) if api_key else []
        modelo = st.selectbox("Modelo IA:", opcoes, index=0) if opcoes else None

    st.title("Dashboard Analista Balanço (v 8.0)")
    
    if not dados_iniciais:
        st.info("👋 **Pronto!** Envie o PDF ou Excel no menu lateral.")
        st.markdown("""<div class="footer">Relatório criado por INOVALENIN Soluções em Tecnologias - www.inovalenin.com.br - atendimento@inovalenin.com.br</div>""", unsafe_allow_html=True)
        st.stop()

    # --- ÁREA DE CONFERÊNCIA E EDIÇÃO (AGORA COM DRE COMPLETA) ---
    st.markdown("### 🔍 Conferência de Dados (DRE Detalhada)")
    
    bp = dados_iniciais['bp']
    dre = dados_iniciais['dre']
    
    check_zeros = (dre.receita_bruta == 0 or dre.lucro_liquido == 0 or dre.custos == 0)
    if check_zeros:
        st.warning("⚠️ Alguns campos da DRE não foram detectados. Preencha abaixo para habilitar os índices avançados.")

    with st.expander("📝 Editar/Corrigir Valores Extraídos (Clique para abrir)", expanded=check_zeros):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("##### 1. Receita")
            dre.receita_bruta = st.number_input("Receita Bruta", value=dre.receita_bruta, format="%.2f")
            dre.deducoes = st.number_input("(-) Deduções", value=dre.deducoes, format="%.2f")
            # Receita Liquida é calculada ou ajustada
            val_rl = dre.receita_bruta - dre.deducoes
            st.caption(f"Receita Líquida Calc: {val_rl:,.2f}")
            dre.receita_liquida = st.number_input("Receita Líquida (Oficial)", value=(dre.receita_liquida if dre.receita_liquida > 0 else val_rl), format="%.2f")
        
        with c2:
            st.markdown("##### 2. Custos & Despesas")
            dre.custos = st.number_input("(-) Custos (CMV/CPV)", value=dre.custos, format="%.2f")
            dre.despesas_operacionais = st.number_input("(-) Despesas Operacionais", value=dre.despesas_operacionais, format="%.2f")
            # Lucro Bruto Calc
            val_lb = dre.receita_liquida - dre.custos
            st.caption(f"Lucro Bruto Calc: {val_lb:,.2f}")
            dre.lucro_bruto = st.number_input("Lucro Bruto (Oficial)", value=(dre.lucro_bruto if dre.lucro_bruto != 0 else val_lb), format="%.2f")

        with c3:
            st.markdown("##### 3. Resultado")
            dre.resultado_operacional = st.number_input("Resultado Operacional (EBIT)", value=dre.resultado_operacional, format="%.2f")
            dre.lucro_liquido = st.number_input("(=) Lucro/Prejuízo Líquido", value=dre.lucro_liquido, format="%.2f")
            
            st.markdown("---")
            st.markdown("**Balanço Resumido**")
            bp.ativo_circulante = st.number_input("Ativo Circ.", value=bp.ativo_circulante, format="%.2f")
            bp.passivo_circulante = st.number_input("Passivo Circ.", value=bp.passivo_circulante, format="%.2f")
            bp.estoques = st.number_input("Estoques", value=bp.estoques, format="%.2f")

    # Recalcula índices com dados novos
    analista = AnalistaFinanceiro(bp, dre)
    kpis = analista.calcular_kpis()
    score = analista.gerar_score(kpis)

    # --- DASHBOARD DE INDICADORES ---
    st.divider()
    st.subheader("📊 Indicadores Financeiros")
    
    # Linha 1: Balanço (Liquidez)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Liquidez Corrente", f"{kpis['Liquidez Corrente']:.2f}")
    c2.metric("Liquidez Seca", f"{kpis['Liquidez Seca']:.2f}")
    c3.metric("Endividamento Geral", f"{kpis['Endividamento Geral (%)']:.1f}%")
    c4.metric("Score de Crédito", f"{score}/100")

    # Linha 2: DRE (Rentabilidade - NOVO!)
    st.markdown("##### Performance & Rentabilidade (Análise Vertical)")
    d1, d2, d3, d4, d5 = st.columns(5)
    
    d1.metric("Margem Bruta", f"{kpis['Margem Bruta (%)']:.1f}%", help="Lucro Bruto / Rec. Líquida")
    d2.metric("Margem Operacional", f"{kpis['Margem Operacional (%)']:.1f}%", help="Res. Operacional / Rec. Líquida")
    d3.metric("Margem Líquida", f"{kpis['Margem Líquida (%)']:.1f}%", help="Lucro Líquido / Rec. Líquida")
    d4.metric("GAO (Alavancagem)", f"{kpis['GAO (Alavancagem)']:.2f}", help="Lucro Bruto / Lucro Operacional")
    d5.metric("Peso Desp. Oper.", f"{kpis['Índice Desp. Operacionais (%)']:.1f}%", help="Despesas / Rec. Líquida")

    with st.expander("📐 Ver Fórmulas e Notas Explicativas"):
        st.markdown("""
        **Indicadores de DRE (Novos):**
        * **Margem Bruta:** Eficiência da produção/aquisição. Quanto sobra após pagar o custo direto.
        * **Margem Operacional:** Eficiência da operação. Quanto sobra após pagar custos + despesas (aluguel, pessoal, energia).
        * **GAO (Grau de Alavancagem Operacional):** Mede o risco operacional. Se alto, um aumento nas vendas gera grande aumento no lucro, mas uma queda nas vendas gera grande prejuízo.
        * **Peso Desp. Operacionais:** Quanto da receita é consumido para manter a empresa aberta (custos fixos).
        """)

    st.divider()
    st.subheader("📝 Relatório de Análise Financeira")
    if st.button("✨ Gerar Análise Automatizada (v8.0)", type="primary"):
        if not periodo_final:
            st.warning("⚠️ Informe o PERÍODO no menu lateral.")
        elif modelo and api_key:
            with st.spinner(f"A Rede Neural INOVALENIN está analisando {nome_final}..."):
                texto_ia = consultar_ia_financeira(api_key, modelo, kpis, dre, nome_final, cnpj_final, periodo_final)
                st.session_state['relatorio_gerado'] = texto_ia
        else:
            st.error("Erro de API Key.")

    if st.session_state['relatorio_gerado']:
        with st.container(border=True):
            st.markdown(st.session_state['relatorio_gerado'])
        pdf_bytes = gerar_pdf_final(st.session_state['relatorio_gerado'], nome_final, cnpj_final, periodo_final)
        st.download_button(label="📥 Baixar PDF Completo", data=pdf_bytes, file_name=f"Analise_{nome_final}.pdf", mime='application/pdf')

    st.markdown("""<div class="footer">Relatório criado por INOVALENIN Soluções em Tecnologias - www.inovalenin.com.br - atendimento@inovalenin.com.br</div>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()