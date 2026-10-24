import os
import re
import json
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# Força o carregamento do ficheiro .env na mesma pasta
load_dotenv(override=True)

# Vai buscar a chave ao cofre
chave_api = os.getenv("GOOGLE_API_KEY")

if not chave_api:
    raise RuntimeError("ERRO: O Python não encontrou a chave no ficheiro .env. Verifique o nome do ficheiro.")

genai.configure(api_key=chave_api)
modelo = genai.GenerativeModel('gemini-3.8-flash')

# 2. Prompt mais rigoroso para focar a IA e evitar aspas que quebram o código
PROMPT_SISTEMA = """
És um jornalista especialista em Google Discover e SEO Local no Brasil.
Tarefa: Escreve APENAS UMA ÚNICA notícia focada estritamente no tema fornecido. Não mistures assuntos.
Devolve o resultado ESTRITAMENTE num formato JSON válido, com as seguintes chaves exatas:
"titulo": (máximo 60 caracteres, NUNCA uses aspas aqui dentro, foco em impacto)
"categoria": (uma palavra curta, ex: Trabalho, INSS, Tributário)
"resumo": (máximo 150 caracteres, NUNCA uses aspas aqui dentro)
"description": (texto otimizado para SEO, NUNCA uses aspas aqui dentro)
"geo_region": (ex: BR, BR-SP)
"texto_artigo": (O corpo da notícia. Usa parágrafos curtos. Divide com subtítulos usando ##).

Não envies NENHUM texto fora do JSON. Não uses blocos de código (```json).
"""

def gerar_conteudo_ia(tema):
    print(f"A redigir artigo sobre: '{tema}'...")
    resposta = modelo.generate_content(f"{PROMPT_SISTEMA}\n\nTema: {tema}")
    
    try:
        # Limpa resíduos e garante a extração do JSON
        texto_limpo = resposta.text.replace('```json', '').replace('```', '').strip()
        dados = json.loads(texto_limpo)
        return dados
    except json.JSONDecodeError as e:
        print("Erro: A IA não devolveu um JSON válido. Tentando novamente na próxima execução.")
        return None

def publicar_noticia_no_site(dados_ia, url_imagem):
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    nome_seguro = re.sub(r'[^a-z0-9]+', '-', dados_ia["titulo"].lower().strip()).strip('-')
    caminho_ficheiro = os.path.join("src", "content", "blog", f"{nome_seguro}.mdx")
    
    # BLINDAGEM PARA A NETLIFY: Substitui qualquer aspa dupla acidental por aspa simples
    titulo_limpo = dados_ia['titulo'].replace('"', "'")
    desc_limpa = dados_ia['description'].replace('"', "'")
    resumo_limpo = dados_ia['resumo'].replace('"', "'")
    
    bloco_adsense = """
<div style="background: #e2e8f0; padding: 2rem; text-align: center; margin: 2rem 0; font-weight: bold; color: #475569; border-radius: 8px;">
  💰 Espaço para o Bloco de Anúncio AdSense 💰
</div>
"""
    
    # Injeta o AdSense no centro do texto
    paragrafos = dados_ia["texto_artigo"].split('\n\n')
    meio = len(paragrafos) // 2
    paragrafos.insert(meio, bloco_adsense)
    texto_com_anuncio = '\n\n'.join(paragrafos)

    # Criação do ficheiro com a blindagem ativada e imagem injetada
    conteudo_final = f"""---
title: "{titulo_limpo}"
date: "{data_hoje}"
category: "{dados_ia['categoria']}"
image: "{url_imagem}"
excerpt: "{resumo_limpo}"
description: "{desc_limpa}"
geo_region: "{dados_ia['geo_region']}"
---

{texto_com_anuncio}
"""

    os.makedirs(os.path.dirname(caminho_ficheiro), exist_ok=True)
    with open(caminho_ficheiro, "w", encoding="utf-8") as ficheiro:
        ficheiro.write(conteudo_final)
        
    print(f"✅ Artigo injetado no Astro com sucesso: {caminho_ficheiro}")

# ==========================================
# PAINEL DE CONTROLO DO GERADOR (AGORA COM IMAGENS AUTOMÁTICAS)
# ==========================================
# Mapeia cada tema para a sua imagem guardada na pasta public/imagens/
temas_para_gerar = [
    {
        "tema": "Novas regras de aposentadoria do INSS para 2027",
        "imagem": "/imagens/aposentado-inss.webp" 
    },
    {
        "tema": "Trabalhador sem carteira assinada tem direito a férias?",
        "imagem": "/imagens/carteira-trabalho.webp"
    },
    {
        "tema": "Governo anuncia mudanças no teto do seguro-desemprego",
        "imagem": "/imagens/seguro-desemprego.webp"
    }
]

# O gerador foca-se num bloco (tema + imagem) de cada vez
for item in temas_para_gerar:
    artigo_gerado = gerar_conteudo_ia(item["tema"])
    if artigo_gerado:
        publicar_noticia_no_site(artigo_gerado, item["imagem"])