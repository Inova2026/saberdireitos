import os
import re
import json
from datetime import datetime
import google.generativeai as genai

# 1. Configuração da IA
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("Defina a variável de ambiente GOOGLE_API_KEY para usar o gerador.")
genai.configure(api_key=api_key)
modelo = genai.GenerativeModel('gemini-3.8-flash')

# 2. O Prompt que obriga a IA a devolver uma estrutura de dados perfeita (JSON)
PROMPT_SISTEMA = """
És um jornalista especialista em Google Discover e SEO Local no Brasil.
Escreve uma notícia sobre o tema fornecido.
Devolve o resultado ESTRITAMENTE num formato JSON válido, com as seguintes chaves exatas:
"titulo": (máximo 60 caracteres, foco em impacto imediato)
"categoria": (uma palavra curta, ex: Trabalho, INSS, Tributário)
"resumo": (máximo 150 caracteres para o resumo do cartão)
"description": (texto otimizado para a meta tag de SEO)
"geo_region": (ex: BR, BR-SP)
"texto_artigo": (O corpo da notícia. Usa parágrafos curtos de 3 linhas. Foca no impacto local logo no 1º parágrafo. Divide o texto com subtítulos usando ##).

Não envies NENHUM texto fora do JSON. Não uses formatação markdown em volta do JSON.
"""

def gerar_conteudo_ia(tema):
    print(f"A redigir artigo sobre: '{tema}'...")
    resposta = modelo.generate_content(f"{PROMPT_SISTEMA}\n\nTema: {tema}")
    
    try:
        # Limpa resíduos de formatação que a IA possa enviar e extrai os dados
        texto_limpo = resposta.text.replace('```json', '').replace('```', '').strip()
        dados = json.loads(texto_limpo)
        return dados
    except json.JSONDecodeError as e:
        print("Erro: A IA não devolveu um JSON válido.")
        return None

def publicar_noticia_no_site(dados_ia, url_imagem):
    url_imagem_limpa = re.sub(r'^[^h]*http', 'http', url_imagem.strip())
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    nome_seguro = re.sub(r'[^a-z0-9]+', '-', dados_ia["titulo"].lower().strip()).strip('-')
    caminho_ficheiro = os.path.join("src", "content", "blog", f"{nome_seguro}.mdx")
    
    bloco_adsense = """
<div style="background: #e2e8f0; padding: 2rem; text-align: center; margin: 2rem 0; font-weight: bold; color: #475569; border-radius: 8px;">
  💰 Espaço para o Bloco de Anúncio AdSense 💰
</div>
"""
    
    # Divide os parágrafos e injeta o AdSense no centro matemático do texto
    paragrafos = dados_ia["texto_artigo"].split('\n\n')
    meio = len(paragrafos) // 2
    paragrafos.insert(meio, bloco_adsense)
    texto_com_anuncio = '\n\n'.join(paragrafos)

    conteudo_final = f"""---
title: "{dados_ia['titulo']}"
date: "{data_hoje}"
category: "{dados_ia['categoria']}"
image: "{url_imagem_limpa}"
excerpt: "{dados_ia['resumo']}"
description: "{dados_ia['description']}"
geo_region: "{dados_ia['geo_region']}"
---

{texto_com_anuncio}
"""

    os.makedirs(os.path.dirname(caminho_ficheiro), exist_ok=True)
    with open(caminho_ficheiro, "w", encoding="utf-8") as ficheiro:
        ficheiro.write(conteudo_final)
        
    print(f"✅ Artigo injetado no Astro com sucesso: {caminho_ficheiro}")

# ==========================================
# PAINEL DE CONTROLO DO GERADOR
# ==========================================
temas_para_gerar = [
    "Novas regras de aposentadoria do INSS para 2027",
    "Trabalhador sem carteira assinada tem direito a férias?",
    "Governo anuncia mudanças no teto do seguro-desemprego"
]
imagem_base = "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=800&q=80"

for tema in temas_para_gerar:
    artigo_gerado = gerar_conteudo_ia(tema)
    if artigo_gerado:
        publicar_noticia_no_site(artigo_gerado, imagem_base)