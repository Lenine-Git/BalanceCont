import streamlit as st
import pandas as pd
import re
import pdfplumber
import google.generativeai as genai
from dataclasses import dataclass
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="INOVALENIN - Financial Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        pc = self.bp.passivo_circulante if self.bp.passivo_circulante > 0 else 1
        # Passivo Exigível Total = Circulante + Não Circulante
        passivo_exigivel = pc + self.bp.passivo_nao_circulante
        
        # Ativo Total
        at = self.bp.ativo_total if self.bp.ativo_total > 0 else 1
        rb = self.dre.receita_bruta if self.dre.receita_bruta > 0 else 1

        return {
            "Liquidez Corrente": self.bp.ativo_circulante / pc,
            "Liquidez Seca": (self.bp.ativo_circulante - self.bp.estoques) / pc,
            "Liquidez Geral": (self.bp.ativo_circulante + self.bp.ativo_nao_circulante) / passivo_exigivel,
            "Endividamento Geral (%)": (passivo_exigivel / at) * 100,
            "Margem Líquida (%)": (self.dre.lucro_liquido / rb) * 100
        }

    def gerar_score(self, kpis):
        score = 50
        # Score calibrado
        if kpis["Liquidez Corrente"] >= 1.0: score += 20
        elif kpis["Liquidez Corrente"] < 0.8: score -= 15
        
        if kpis["Liquidez Seca"] > 0.5: score += 10
        
        endiv = kpis["Endividamento Geral (%)"]
        if endiv < 60: score += 15
        elif endiv > 100: score -= 25 # Passivo a descoberto
        
        margem = kpis["Margem Líquida (%)"]
        if margem > 5: score += 20
        elif margem < 0: score -= 20
        
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

def consultar_ia_financeira(api_key, modelo_escolhido, kpis, dados_dre, nome_empresa, cnpj_empresa):
    if not api_key: return "⚠️ Insira a chave API."

    contexto = f"Empresa: {nome_empresa} (CNPJ: {cnpj_empresa})"
    
    prompt = f"""
    {contexto}
    Atue como um Analista Financeiro Sênior e Consultor Estratégico.
    Gere um Relatório Gerencial de Análise Financeira detalhado.
    Evite termos como "Auditoria". Use "Análise", "Diagnóstico".
    
    DADOS APURADOS:
    - Liquidez Corrente: {kpis['Liquidez Corrente']:.2f}
    - Liquidez Seca: {kpis['Liquidez Seca']:.2f}
    - Liquidez Geral: {kpis['Liquidez Geral']:.2f}
    - Endividamento Geral: {kpis['Endividamento Geral (%)']:.1f}%
    - Margem Líquida: {kpis['Margem Líquida (%)']:.1f}%
    - Receita Bruta: R$ {dados_dre.receita_bruta:,.2f}
    - Resultado Líquido: R$ {dados_dre.lucro_liquido:,.2f}

    ESTRUTURA OBRIGATÓRIA (Siga estritamente estes tópicos em Markdown):
    
    # 1. Identificação da empresa analisada
    [Nome, CNPJ e breve contexto sobre o porte baseado na receita]

    # 2. Índices Financeiros
    ## 2.1 Análise dos índices financeiros detalhada
    [Analise cada índice. Ex: "A liquidez corrente de X indica que para cada R$ 1 de dívida, há R$ Y de ativos..."]
    
    ## 2.2 Notas explicativas de cada índice financeiro analisado
    [Breve glossário didático do que é cada índice]

    # 3. Análise estruturada
    ## 3.1 Análise geral
    [Visão macro da saúde financeira. A empresa é solvente? É lucrativa?]
    ## 3.2 Pontos Positivos
    [Lista de bullets]
    ## 3.3 Pontos críticos/inconsistências
    [Lista de bullets. Se houver prejuízo ou passivo a descoberto, destaque aqui]

    # 4. Conclusão Técnica
    [Parecer final do analista]
    ## 4.1 Recomendações Técnicas
    [3 a 5 ações práticas para a gestão]
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
        self.cell(0, 10, 'INOVALENIN Solucoes em Tecnologia - 2025', 0, 0, 'C')

def gerar_pdf_final(texto_ia, nome, cnpj):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Cabeçalho Empresa
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, f"EMPRESA: {nome}", 0, 1)
    pdf.cell(0, 8, f"CNPJ: {cnpj}", 0, 1)
    pdf.line(10, 35, 200, 35)
    pdf.ln(10)
    
    # Conteúdo da IA
    pdf.set_font("Arial", size=10)
    # Limpeza básica para PDF (latin-1 não suporta emojis ou markdown rico)
    texto_limpo = texto_ia.replace('**', '').replace('##', '').replace('#', '')
    texto_limpo = texto_limpo.encode('latin-1', 'replace').decode('latin-1')
    
    pdf.multi_cell(0, 5, texto_limpo)
    
    return pdf.output(dest='S').encode('latin-1')

# --- 5. EXTRAÇÃO INTELIGENTE (CORREÇÃO DE VALORES) ---
def smart_float(v_str):
    """Detecta automaticamente se é 1.000,00 ou 1.000.00"""
    if not v_str: return 0.0
    # Remove letras D/C e espaços
    clean = re.sub(r'[a-zA-Z\s]', '', v_str)
    
    # Lógica de detecção de formato
    if ',' in clean and '.' in clean: 
        # Formato BR padrão (1.234,56)
        clean = clean.replace('.', '').replace(',', '.')
    elif clean.count('.') == 1 and ',' not in clean:
        # Pode ser 1234.56 (US) ou 1234 (BR milhar sem decimal). 
        # Vamos assumir US se tiver 2 casas decimais no final (ex: .87 do seu PDF)
        parts = clean.split('.')
        if len(parts[-1]) == 2:
            pass # Já é float python
        else:
            clean = clean.replace('.', '') # Era milhar
    elif clean.count('.') > 1:
         # 1.234.567 -> 1234567
         clean = clean.replace('.', '')
    elif ',' in clean:
         clean = clean.replace(',', '.')
         
    try:
        return float(clean)
    except:
        return 0.0

def extrair_dados_pdf(texto):
    """
    Busca valores usando regex que prioriza a linha onde o label está.
    """
    # Regex para pegar número no final da linha ou logo após label
    # Captura: 335.909.87 ou 335.909,87, opcionalmente seguido de D ou C
    rx_num = r"([\d\.,]+)\s*[DC]?"
    
    def buscar(labels, contexto_negativo=[]):
        for label in labels:
            # Procura a linha que contem o label
            pattern = re.compile(f"({label}).*?{rx_num}", re.IGNORECASE)
            matches = pattern.findall(texto)
            
            for match in matches:
                # match é tupla: (LabelEncontrado, Valor)
                val_str = match[1]
                
                # Validação extra: Se tiver contexto negativo na mesma linha (ex: "Não Circulante") ignora
                linha_completa = texto[texto.find(label):texto.find(val_str)+len(val_str)+10]
                if any(neg in linha_completa.upper() for neg in contexto_negativo):
                    continue
                
                val = smart_float(val_str)
                if val > 0: return val
        return 0.0

    # 1. ATIVO CIRCULANTE (Exclui "Total" para não pegar a soma errada)
    ac = buscar(["ATIVO CIRCULANTE"], contexto_negativo=["TOTAL", "NAO CIRCULANTE"])
    # Se falhar, tenta pegar o valor explícito se estiver formatado como "Total do Ativo Circulante"
    if ac == 0: ac = buscar(["Total do Ativo Circulante"])

    # 2. PASSIVO CIRCULANTE
    pc = buscar(["PASSIVO CIRCULANTE"], contexto_negativo=["TOTAL", "NAO CIRCULANTE"])
    
    # 3. ESTOQUES
    est = buscar(["ESTOQUES", "MERCADORIAS", "ESTOQUE FINAL"])
    
    # 4. ATIVO NAO CIRCULANTE (REALIZAVEL LONGO PRAZO)
    anc = buscar(["ATIVO NAO CIRCULANTE", "REALIZAVEL A LONGO PRAZO", "PERMANENTE", "IMOBILIZADO"])
    
    # 5. PASSIVO NAO CIRCULANTE
    pnc = buscar(["PASSIVO NAO CIRCULANTE", "EXIGIVEL A LONGO PRAZO"])

    # 6. DRE
    rb = buscar(["RECEITA BRUTA", "RECEITA OPERACIONAL BRUTA"])
    lucro = buscar(["LUCRO LIQUIDO", "RESULTADO LIQUIDO"])
    if lucro == 0:
        prej = buscar(["PREJUIZO DO PERIODO", "PREJUIZO"])
        if prej > 0: lucro = -prej

    return {
        "ac": ac, "anc": anc, 
        "pc": pc, "pnc": pnc,
        "est": est, "rb": rb, "lucro": lucro
    }

def processar_pdf_com_plumber(uploaded_file):
    if uploaded_file is None: return None, None
    texto_full = ""
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                texto_full += page.extract_text() + "\n"
    except Exception as e:
        st.error(f"Erro leitura PDF: {e}")
        return None, None
    
    # Identificação
    nome = "Empresa Analisada"
    match_nome = re.search(r"(?:Nome|Empresa)\s*[:\n-]+\s*(.{5,60})", texto_full, re.IGNORECASE)
    if match_nome: nome = match_nome.group(1).strip().split('\n')[0]
    
    match_cnpj = re.search(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", texto_full)
    cnpj = match_cnpj.group(0) if match_cnpj else ""

    # Extração Valores
    v = extrair_dados_pdf(texto_full)
    
    # Monta objetos
    dados = {
        "bp": BalancoPatrimonial(v['ac'], v['anc'], v['pc'], v['pnc'], 0, v['est']),
        "dre": DRE(v['rb'], v['lucro'])
    }
    return dados, (nome, cnpj)

# --- 6. INTERFACE ---
def main():
    st.markdown("""
        <style>
        @media print { .stSidebar {display: none;} }
        .footer {position: fixed; left: 0; bottom: 0; width: 100%; background-color: #f1f1f1; color: #666; text-align: center; padding: 10px; font-size: 12px; z-index: 100;}
        </style>
    """, unsafe_allow_html=True)

    # Variáveis de Estado (Controle de Limpeza)
    if 'uploader_key' not in st.session_state: st.session_state['uploader_key'] = 0
    if 'nome_empresa' not in st.session_state: st.session_state['nome_empresa'] = ""
    if 'cnpj_empresa' not in st.session_state: st.session_state['cnpj_empresa'] = ""
    if 'relatorio_gerado' not in st.session_state: st.session_state['relatorio_gerado'] = ""

    with st.sidebar:
        st.header("⚙️ Configurações")
        
        # O key=... é o segredo para limpar o arquivo
        uploaded_file = st.file_uploader(
            "📂 Balanço + DRE (PDF)", 
            type="pdf", 
            key=f"uploader_{st.session_state['uploader_key']}"
        )
        
        # Botão Limpar
        if st.button("🗑️ Limpar / Novo Arquivo", use_container_width=True):
            st.session_state['uploader_key'] += 1 # Troca a chave, resetando o uploader
            st.session_state['nome_empresa'] = ""
            st.session_state['cnpj_empresa'] = ""
            st.session_state['relatorio_gerado'] = ""
            st.rerun()

        st.markdown("---")
        st.write("🏢 **Identificação**")
        if uploaded_file:
            dados, info = processar_pdf_com_plumber(uploaded_file)
            if dados:
                if info[0] != "Empresa Analisada": st.session_state['nome_empresa'] = info[0]
                st.session_state['cnpj_empresa'] = info[1]
        else:
            dados = None

        nome_final = st.text_input("Razão Social:", value=st.session_state['nome_empresa'])
        cnpj_final = st.text_input("CNPJ:", value=st.session_state['cnpj_empresa'])
        
        st.markdown("---")
        api_key = st.text_input("Google API Key", type="password")
        
        opcoes = []
        model_idx = 0
        if api_key:
            opcoes = listar_modelos_disponiveis(api_key)
            for i, m in enumerate(opcoes):
                if "flash" in m: model_idx = i; break
        
        modelo = st.selectbox("Modelo IA:", opcoes, index=model_idx) if opcoes else None

    st.title("📊 Dashboard Financeiro Pro (v7.1)")
    
    if not dados:
        # Mensagem amigável de "Estado Limpo"
        st.info("👋 **Pronto para analisar outro arquivo!** Pode enviar o PDF no menu lateral.")
        st.stop()

    analista = AnalistaFinanceiro(dados['bp'], dados['dre'])
    kpis = analista.calcular_kpis()
    score = analista.gerar_score(kpis)

    # --- MÉTRICAS ---
    col_score, col_kpis = st.columns([1, 4])
    with col_score:
        st.metric("Score", f"{score}/100")
    
    with col_kpis:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Liquidez Corrente", f"{kpis['Liquidez Corrente']:.2f}", help="Ativo Circulante / Passivo Circulante")
        c2.metric("Liquidez Seca", f"{kpis['Liquidez Seca']:.2f}", help="(Ativo Circulante - Estoques) / Passivo Circulante")
        c3.metric("Liquidez Geral", f"{kpis['Liquidez Geral']:.2f}", help="(AC + ARLP) / (PC + ELP)")
        c4.metric("Margem Líquida", f"{kpis['Margem Líquida (%)']:.1f}%", help="Lucro Líquido / Receita Bruta")

    with st.expander("📐 Ver Fórmulas Utilizadas (Detalhamento Técnico)"):
        st.markdown("""
        * **Liquidez Corrente:** $\\frac{\\text{Ativo Circulante}}{\\text{Passivo Circulante}}$
        * **Liquidez Seca:** $\\frac{\\text{Ativo Circulante} - \\text{Estoques}}{\\text{Passivo Circulante}}$
        * **Liquidez Geral:** $\\frac{\\text{AC} + \\text{ARLP}}{\\text{PC} + \\text{ELP}}$
        * **Margem Líquida:** $\\frac{\\text{Lucro Líquido}}{\\text{Receita Bruta}} \\times 100$
        """)

    st.divider()

    # --- GERAÇÃO DE ANÁLISE ---
    st.subheader("📝 Relatório de Análise Financeira")
    
    if st.button("✨ Gerar Análise Automatizada", type="primary"):
        if modelo and api_key:
            with st.spinner(f"Processando análise para {nome_final}..."):
                texto_ia = consultar_ia_financeira(api_key, modelo, kpis, dados['dre'], nome_final, cnpj_final)
                st.session_state['relatorio_gerado'] = texto_ia
        else:
            st.error("Configure a API Key no menu lateral.")

    if st.session_state['relatorio_gerado']:
        with st.container(border=True):
            st.markdown(st.session_state['relatorio_gerado'])
        
        pdf_bytes = gerar_pdf_final(st.session_state['relatorio_gerado'], nome_final, cnpj_final)
        st.download_button(
            label="📥 Baixar PDF",
            data=pdf_bytes,
            file_name=f"Analise_{nome_final}.pdf",
            mime='application/pdf'
        )

    st.markdown("""
    <div class="footer">
    © INOVALENIN Soluções em Tecnologia - 2025
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()