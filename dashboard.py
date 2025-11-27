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
    page_title="INOVALENIN - Acesso Restrito",
    page_icon="🔒",
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
                    if usuario == "admin_lenine": 
                        st.session_state['user_role'] = "admin"
                    else:
                        st.session_state['user_role'] = "cliente"
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
        st.info("Gerencie usuários através dos Secrets do Streamlit Cloud.")

st.sidebar.title(f"👤 {st.session_state['username']}")
if st.sidebar.button("Sair / Logout"):
    st.session_state['logged_in'] = False
    st.rerun()

# ==============================================================================
# LÓGICA DO DASHBOARD (VERSÃO 7.9 REFINADA)
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
        rb = self.dre.receita_bruta if self.dre.receita_bruta > 0 else 1.0

        return {
            "Liquidez Corrente": self.bp.ativo_circulante / pc,
            "Liquidez Seca": (self.bp.ativo_circulante - self.bp.estoques) / pc,
            "Liquidez Geral": (self.bp.ativo_circulante + self.bp.ativo_nao_circulante) / passivo_exigivel,
            "Endividamento Geral (%)": (passivo_exigivel / at) * 100,
            "Margem Líquida (%)": (self.dre.lucro_liquido / rb) * 100
        }

    def gerar_score(self, kpis):
        score = 50
        lc = kpis["Liquidez Corrente"]
        if lc >= 1.5: score += 20
        elif lc >= 1.0: score += 10
        elif lc < 0.8: score -= 15
        
        ls = kpis["Liquidez Seca"]
        if ls > 1.0: score += 10
        
        eg = kpis["Endividamento Geral (%)"]
        if eg < 50: score += 15
        elif eg > 80: score -= 20
        
        ml = kpis["Margem Líquida (%)"]
        if ml > 10: score += 20
        elif ml < 0: score -= 25
        
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
    
    # Prompt refinado para tom mais humano e profissional, com disclaimer explícito
    prompt = f"""
    {contexto}
    Atue como um Analista Financeiro Sênior da INOVALENIN.
    Sua tarefa é gerar um Relatório Gerencial detalhado com base nos dados fornecidos.
    
    DIRETRIZES DE TOM E ESTILO:
    - O texto deve ser profissional, direto e técnico, mas acessível a gestores.
    - Evite soar robótico. Use conectivos e frases bem construídas.
    - Deixe explícito no início que esta análise foi gerada automaticamente pela rede neural da INOVALENIN.
    
    DADOS APURADOS:
    - Liquidez Corrente: {kpis['Liquidez Corrente']:.2f}
    - Liquidez Seca: {kpis['Liquidez Seca']:.2f}
    - Liquidez Geral: {kpis['Liquidez Geral']:.2f}
    - Endividamento Geral: {kpis['Endividamento Geral (%)']:.1f}%
    - Margem Líquida: {kpis['Margem Líquida (%)']:.1f}%
    - Receita Bruta: R$ {dados_dre.receita_bruta:,.2f}
    - Resultado Líquido: R$ {dados_dre.lucro_liquido:,.2f}

    ESTRUTURA OBRIGATÓRIA (Markdown):
    
    # 1. Identificação e Contexto
    [Inicie confirmando que este relatório é uma análise automática da INOVALENIN. Cite Nome, CNPJ e Período]

    # 2. Índices Financeiros
    ## 2.1 Análise Detalhada
    [Analise cada índice com profundidade, correlacionando-os quando possível]
    ## 2.2 Notas Explicativas
    [Breve glossário técnico dos termos usados]

    # 3. Análise Estruturada
    ## 3.1 Visão Geral
    [Diagnóstico macro da saúde financeira]
    ## 3.2 Pontos Positivos
    [Destaques favoráveis]
    ## 3.3 Pontos de Atenção
    [Riscos e inconsistências]

    # 4. Conclusão Técnica e Recomendações
    [Parecer final sintético]
    ## 4.1 Plano de Ação
    [Sugestões práticas]
    
    ---
    [Encerre com este parágrafo EXATO: "Recomendamos que este relatório seja discutido com a contabilidade da empresa para esclarecimentos mais detalhados. Acesse o site da INOVALENIN (www.inovalenin.com.br) para conhecer mais soluções tecnológicas que auxiliarão na gestão da sua empresa."]
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
        self.cell(0, 10, 'RELATORIO GERENCIAL DE ANALISE FINANCEIRA', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        # Rodapé padronizado conforme solicitado
        rodape_texto = "Relatorio criado por INOVALENIN Solucoes em Tecnologias - www.inovalenin.com.br - atendimento@inovalenin.com.br"
        self.cell(0, 10, rodape_texto, 0, 0, 'C')

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
    # Remove formatação Markdown para PDF limpo
    texto_limpo = texto_ia.replace('**', '').replace('##', '').replace('#', '')
    texto_limpo = texto_limpo.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 5, texto_limpo)
    
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
    match_periodo = re.search(r"(?:Período|Exercício|Competência).*?(\d{2}/\d{2,4}\s+a\s+\d{2}/\d{2,4})", texto_completo, re.IGNORECASE)
    if match_periodo: return match_periodo.group(1).strip()

    datas_encontradas = re.findall(r"(\d{2}/\d{2}/\d{4})", texto_completo)
    data_encerramento = None
    termos_encerramento = ["ENCERRADO", "ENCERRAMENTO", "POSIÇÃO EM", "BASE EM", "EM 31 DE"]
    
    for termo in termos_encerramento:
        match_contexto = re.search(f"{termo}.*?(\d{{2}}/\d{{2}}/\d{{4}})", texto_completo, re.IGNORECASE)
        if match_contexto:
            data_encerramento = match_contexto.group(1)
            break
            
    if not data_encerramento and datas_encontradas:
        try:
            datas_obj = [datetime.strptime(d, "%d/%m/%Y") for d in datas_encontradas]
            datas_obj.sort()
            data_final = datas_obj[-1]
            data_encerramento = data_final.strftime("%d/%m/%Y")
        except: pass

    if data_encerramento:
        dia, mes, ano = data_encerramento.split('/')
        return f"01/01/{ano} a {dia}/{mes}/{ano}"
    return ""

def extrair_dados_texto(texto_completo):
    rx_valor = r"([\d\.,]+)\s*[DC]?" 
    meio_texto = len(texto_completo) // 2
    texto_balanco = texto_completo[:int(len(texto_completo)*0.6)]
    texto_dre = texto_completo[int(len(texto_completo)*0.4):]

    def buscar_valor(labels, texto_alvo, avoid=[]):
        for label in labels:
            pattern = re.compile(f"{label}.*?{rx_valor}", re.IGNORECASE | re.DOTALL)
            match = pattern.search(texto_alvo)
            if match:
                trecho_encontrado = match.group(0)
                if any(bad.upper() in trecho_encontrado.upper() for bad in avoid): continue
                val_str = match.group(1)
                if val_str in ['2023', '2024', '2025', '2022']: continue
                val = parse_br_currency(val_str)
                if val > 0: return val
        return 0.0

    ac = buscar_valor(["ATIVO CIRCULANTE"], texto_balanco, avoid=["TOTAL DO ATIVO CIRCULANTE", "PASSIVO"])
    if ac == 0: ac = buscar_valor(["Total do Ativo Circulante"], texto_balanco)
    pc = buscar_valor(["PASSIVO CIRCULANTE"], texto_balanco, avoid=["TOTAL DO PASSIVO CIRCULANTE", "ATIVO"])
    if pc == 0: pc = buscar_valor(["Total do Passivo Circulante"], texto_balanco)
    est = buscar_valor(["ESTOQUES", "MERCADORIAS", "ESTOQUE FINAL"], texto_balanco)
    anc = buscar_valor(["ATIVO NAO CIRCULANTE", "REALIZAVEL A LONGO PRAZO", "PERMANENTE", "IMOBILIZADO"], texto_balanco, avoid=["TOTAL"])
    pnc = buscar_valor(["PASSIVO NAO CIRCULANTE", "EXIGIVEL A LONGO PRAZO"], texto_balanco, avoid=["TOTAL"])
    at_total = buscar_valor(["TOTAL DO ATIVO"], texto_balanco)
    if at_total > ac and anc < (at_total - ac) * 0.9: anc = at_total - ac
    rb = buscar_valor(["RECEITA BRUTA", "RECEITA OPERACIONAL BRUTA", "VENDAS DE SERVICOS"], texto_dre)
    lucro = buscar_valor(["LUCRO DO PERIODO", "RESULTADO DO PERIODO", "LUCRO LIQUIDO DO EXERCICIO"], texto_dre)
    if lucro == 0:
        prej = buscar_valor(["PREJUIZO DO PERIODO", "PREJUIZO DO EXERCICIO"], texto_dre)
        if prej > 0: lucro = -prej
    if lucro == 0:
        lucro = buscar_valor(["LUCRO LIQUIDO", "RESULTADO LIQUIDO"], texto_dre, avoid=["ACUMULADO", "ANTERIOR"])
    return {"ac": ac, "anc": anc, "pc": pc, "pnc": pnc, "est": est, "rb": rb, "lucro": lucro}

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
        "dre": DRE(v['rb'], v['lucro'])
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
    if 'id_nome' not in st.session_state: st.session_state['id_nome'] = ""
    if 'id_cnpj' not in st.session_state: st.session_state['id_cnpj'] = ""
    if 'id_periodo' not in st.session_state: st.session_state['id_periodo'] = ""

    with st.sidebar:
        st.header("⚙️ Configurações")
        st.info("ℹ️ **Anexar Balanço + DRE em um único arquivo**\nArquivos aceitos: PDF e Excel")
        uploaded_file = st.file_uploader("Carregar Arquivo", type=["pdf", "xlsx", "xls"], key=f"uploader_{st.session_state['uploader_key']}")
        if st.button("🗑️ Limpar / Novo Arquivo", use_container_width=True):
            st.session_state['uploader_key'] += 1
            st.session_state['relatorio_gerado'] = ""
            st.session_state['id_nome'] = ""
            st.session_state['id_cnpj'] = ""
            st.session_state['id_periodo'] = ""
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
        periodo_final = st.text_input("Período/Exercício:", value=st.session_state['id_periodo'], placeholder="Ex: 01/01/2024 a 31/12/2024")
        
        st.markdown("---")
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
            st.success("🔑 IA Conectada.")
        else:
            api_key = st.text_input("Google API Key", type="password")
        
        opcoes = []
        model_idx = 0
        if api_key:
            opcoes = listar_modelos_disponiveis(api_key)
            for i, m in enumerate(opcoes):
                if "flash" in m: model_idx = i; break
        modelo = st.selectbox("Modelo IA:", opcoes, index=model_idx) if opcoes else None

    st.title("Dashboard Analista Balanço (v 7.9)")
    
    if not dados_iniciais:
        st.info("👋 **Pronto para analisar!** Envie o PDF ou Excel no menu lateral.")
        # Rodapé padronizado na tela inicial também
        st.markdown("""<div class="footer">Relatório criado por INOVALENIN Soluções em Tecnologias - www.inovalenin.com.br - atendimento@inovalenin.com.br</div>""", unsafe_allow_html=True)
        st.stop()

    st.markdown("### 🔍 Conferência de Dados")
    bp = dados_iniciais['bp']
    dre = dados_iniciais['dre']
    dados_zerados = (bp.ativo_circulante == 0 or bp.passivo_circulante == 0 or dre.receita_bruta == 0)
    
    if dados_zerados:
        st.error("⚠️ Atenção: Alguns valores críticos não foram encontrados automaticamente.")
    
    with st.expander("📝 Editar/Corrigir Valores Extraídos", expanded=dados_zerados):
        col_edit1, col_edit2 = st.columns(2)
        with col_edit1:
            st.markdown("**Balanço Patrimonial**")
            bp.ativo_circulante = st.number_input("Ativo Circulante", value=bp.ativo_circulante, format="%.2f")
            bp.ativo_nao_circulante = st.number_input("Ativo Não Circulante", value=bp.ativo_nao_circulante, format="%.2f")
            bp.estoques = st.number_input("Estoques", value=bp.estoques, format="%.2f")
        with col_edit2:
            st.markdown("**Passivo & DRE**")
            bp.passivo_circulante = st.number_input("Passivo Circulante", value=bp.passivo_circulante, format="%.2f")
            bp.passivo_nao_circulante = st.number_input("Passivo Não Circulante", value=bp.passivo_nao_circulante, format="%.2f")
            dre.receita_bruta = st.number_input("Receita Bruta", value=dre.receita_bruta, format="%.2f")
            dre.lucro_liquido = st.number_input("Lucro/Prejuízo Líquido", value=dre.lucro_liquido, format="%.2f")

    analista = AnalistaFinanceiro(bp, dre)
    kpis = analista.calcular_kpis()
    score = analista.gerar_score(kpis)

    st.divider()
    col_score, col_kpis = st.columns([1, 4])
    with col_score:
        st.metric("Score", f"{score}/100")
    with col_kpis:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Liquidez Corrente", f"{kpis['Liquidez Corrente']:.2f}", help="AC / PC")
        c2.metric("Liquidez Seca", f"{kpis['Liquidez Seca']:.2f}", help="(AC - Est) / PC")
        c3.metric("Liquidez Geral", f"{kpis['Liquidez Geral']:.2f}", help="(AC+ANC) / (PC+PNC)")
        c4.metric("Margem Líquida", f"{kpis['Margem Líquida (%)']:.1f}%", help="Lucro / Receita")

    with st.expander("📐 Ver Fórmulas Utilizadas"):
        st.markdown("""
        * **Liquidez Corrente:** $\\frac{\\text{Ativo Circulante}}{\\text{Passivo Circulante}}$
        * **Liquidez Seca:** $\\frac{\\text{Ativo Circulante} - \\text{Estoques}}{\\text{Passivo Circulante}}$
        * **Liquidez Geral:** $\\frac{\\text{AC} + \\text{ARLP}}{\\text{PC} + \\text{ELP}}$
        * **Margem Líquida:** $\\frac{\\text{Lucro Líquido}}{\\text{Receita Bruta}} \\times 100$
        """)

    st.divider()
    st.subheader("Relatório de Análise Financeira")
    if st.button("✨ Gerar Análise Automatizada", type="primary"):
        if not periodo_final:
            st.warning("⚠️ Informe o PERÍODO no menu lateral antes de gerar.")
        elif modelo and api_key:
            with st.spinner(f"Processando análise para {nome_final}..."):
                texto_ia = consultar_ia_financeira(api_key, modelo, kpis, dre, nome_final, cnpj_final, periodo_final)
                st.session_state['relatorio_gerado'] = texto_ia
        else:
            st.error("Configure a API Key no menu lateral.")

    if st.session_state['relatorio_gerado']:
        with st.container(border=True):
            st.markdown(st.session_state['relatorio_gerado'])
        pdf_bytes = gerar_pdf_final(st.session_state['relatorio_gerado'], nome_final, cnpj_final, periodo_final)
        st.download_button(label="📥 Baixar PDF", data=pdf_bytes, file_name=f"Analise_{nome_final}.pdf", mime='application/pdf')

    st.markdown("""<div class="footer">Relatório criado por INOVALENIN Soluções em Tecnologias - www.inovalenin.com.br - atendimento@inovalenin.com.br</div>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()