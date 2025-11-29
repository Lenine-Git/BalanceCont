# 📊 BalanceCont Dashboard (v9.0.3)

> **Propriedade Intelectual:** INOVALENIN Soluções em Tecnologias  
> **Programador Sênior:** Paulo Lenine e Equipe

## 📖 Sobre o Projeto

O **BalanceCont Dashboard** é uma solução avançada de *Financial Analytics* desenvolvida em Python (Streamlit). O sistema automatiza a leitura, estruturação e análise de demonstrativos contábeis (Balanço Patrimonial e DRE) a partir de arquivos PDF ou Excel.

Utilizando a API do **Google Gemini (IA Generativa)**, o sistema não apenas calcula indicadores financeiros, mas atua como um Analista Financeiro Virtual, gerando relatórios textuais detalhados sobre a saúde da empresa, com gráficos e diagnósticos precisos.

## 🚀 Funcionalidades Principais

* **Leitura Inteligente (OCR/Regex):** Extração robusta de dados de PDFs contábeis complexos e planilhas Excel.
* **Análise de KPIs:** Cálculo automático de Liquidez (Corrente, Seca, Geral), Margens, EBIT, GAO e Endividamento.
* **Comparação Temporal (YoY):** Análise evolutiva comparando o exercício atual com o anterior.
* **IA Integrada (Google Gemini):** Geração de relatórios gerenciais com linguagem natural, diagnósticos e recomendações estratégicas.
* **Geração de PDF:** Exportação de relatório completo com gráficos (Matplotlib) e tabelas formatadas.
* **Interface Profissional:** * Modo Claro/Escuro com alto contraste.
    * Layout limpo (remoção de marcas do Streamlit).
    * Controle de Acesso (RBAC) para Admin vs Cliente.

## 🛠️ Stack Tecnológica

* **Frontend/Backend:** Python 3.10+, Streamlit
* **Processamento de Dados:** Pandas, Regex
* **Leitura de Arquivos:** PDFPlumber, OpenPyXL
* **Inteligência Artificial:** Google Generative AI (Gemini 2.0 Flash)
* **Visualização:** Altair (Interativo), Matplotlib (Estático para PDF)
* **Relatórios:** FPDF

## ⚙️ Instalação e Configuração

### 1. Pré-requisitos
Certifique-se de ter o Python instalado. Instale as dependências:

```bash
pip install -r requirements.txt