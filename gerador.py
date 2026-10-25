import os
import re
import json
import time
import random
import hashlib
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# ==========================================
# CONFIGURAÇÃO
# ==========================================
load_dotenv(override=True)

chave_api = os.getenv("GOOGLE_API_KEY")
if not chave_api:
    raise RuntimeError("ERRO: O Python não encontrou a chave no ficheiro .env. Verifique o nome do ficheiro.")

genai.configure(api_key=chave_api)

# Modelo válido e atual (gemini-3.8-flash não existe na API do Gemini).
# gemini-3.5-flash é a versão estável (GA) mais recente em out/2026.
NOME_MODELO = "gemini-3.5-flash"
modelo = genai.GenerativeModel(NOME_MODELO)

PASTA_BLOG = os.path.join("src", "content", "blog")
FICHEIRO_HISTORICO = "historico_artigos.json"

# Faixa de tamanho aceite para o corpo do artigo (em palavras).
# Dá margem em torno dos 400-600 pedidos no prompt, pois a IA não acerta no número exato.
LIMITE_PALAVRAS_MIN = 300
LIMITE_PALAVRAS_MAX = 800

# Mete False para não inserir o bloco reservado para o anúncio do AdSense.
INSERIR_BLOCO_ADSENSE = False

MAX_TENTATIVAS_IA = 3          # tentativas por tema em caso de erro/JSON inválido
ARTIGOS_POR_EXECUCAO = 3       # quantos artigos gerar de cada vez que o script corre
PAUSA_ENTRE_CHAMADAS = 15      # segundos, para não rebentar o rate limit

# ==========================================
# BANCO DE TEMAS (pool grande por categoria)
# O script escolhe automaticamente temas ainda não usados no histórico.
# Podes continuar a adicionar temas a estas listas à vontade.
# ==========================================
TEMAS_POR_CATEGORIA = {
    "INSS": [
        "Novas regras de aposentadoria do INSS para 2027",
        "Como funciona a revisão da vida toda do INSS",
        "INSS libera empréstimo consignado com novas condições",
        "Auxílio-doença: como solicitar pelo Meu INSS",
        "Pente-fino do INSS: quem pode perder o benefício",
        "BPC-LOAS: regras atualizadas de quem tem direito",
        "Calendário de pagamento do INSS do próximo mês",
        "Aposentadoria por invalidez: o que mudou nas regras",
        "Perícia médica do INSS: como se preparar",
        "Pensão por morte: novas regras de cálculo do INSS",
        "INSS digital: quais serviços já não precisam de agência",
        "Aposentadoria rural: documentos exigidos pelo INSS",
        "Reajuste do salário mínimo e impacto nos benefícios do INSS",
        "Como contestar um benefício negado pelo INSS",
        "Aposentadoria por tempo de contribuição: regras de transição",
    ],
    "FGTS": [
        "Saque-aniversário do FGTS: como funciona em 2027",
        "FGTS: calendário de liberação do saque extraordinário",
        "Como consultar o saldo do FGTS pelo aplicativo",
        "Demissão sem justa causa: direito à multa do FGTS",
        "FGTS digital: como usar o saldo para financiar imóvel",
        "Rendimento do FGTS: quanto rende por ano",
        "Quem pode sacar o FGTS em caso de doença grave",
        "FGTS para quitar financiamento habitacional: passo a passo",
        "Diferença entre saque-rescisão e saque-aniversário do FGTS",
        "Como sair do saque-aniversário e voltar ao saque-rescisão",
        "FGTS de trabalhador doméstico: como funciona",
        "Golpes envolvendo o FGTS: como se proteger",
    ],
    "Trabalho CLT": [
        "Trabalhador sem carteira assinada tem direito a férias?",
        "Governo anuncia mudanças no teto do seguro-desemprego",
        "Banco de horas: regras atualizadas da CLT",
        "Trabalho remoto: direitos garantidos pela CLT",
        "Hora extra: como calcular corretamente segundo a CLT",
        "Demissão por justa causa: quais são os motivos previstos em lei",
        "13º salário: regras de pagamento e quem tem direito",
        "Férias vencidas: o que a empresa é obrigada a pagar",
        "Acordo de trabalho intermitente: como funciona na prática",
        "Estabilidade da gestante: regras da CLT",
        "Assédio moral no trabalho: como denunciar",
        "Vale-transporte: obrigatoriedade e regras de desconto",
        "Período de experiência: direitos do trabalhador na CLT",
        "Rescisão indireta: quando o trabalhador pode pedir",
    ],
}

PROMPT_SISTEMA = """
És um jornalista especialista em Google Discover e SEO Local no Brasil.
Tarefa: Escreve APENAS UMA ÚNICA notícia focada estritamente no tema fornecido. Não mistures assuntos.
Devolve o resultado ESTRITAMENTE num formato JSON válido, com as seguintes chaves exatas:
"titulo": (máximo 60 caracteres, NUNCA uses aspas aqui dentro, foco em impacto)
"categoria": (uma palavra curta, ex: Trabalho, INSS, Tributário)
"resumo": (máximo 150 caracteres, NUNCA uses aspas aqui dentro)
"description": (texto otimizado para SEO, NUNCA uses aspas aqui dentro)
"geo_region": (ex: BR, BR-SP)
"texto_artigo": (O corpo da notícia, entre 400 e 600 palavras. Usa parágrafos curtos, de 2 a 4 frases. Divide o texto em 3 a 4 subtítulos usando ##, cobrindo: contexto/o que mudou, quem é afetado, como proceder na prática. Não enroles para atingir o tamanho nem cortes informação importante para ficar curto — fica dentro da faixa pedida.)

Não envies NENHUM texto fora do JSON. Não uses blocos de código (```json).
Não repitas informação nem títulos de artigos já publicados, listados abaixo em "Artigos já publicados".
"""


# ==========================================
# HISTÓRICO (evita repetir temas e artigos)
# ==========================================
def carregar_historico():
    if os.path.exists(FICHEIRO_HISTORICO):
        with open(FICHEIRO_HISTORICO, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Histórico corrompido, a começar um novo.")
    return {"temas_usados": [], "titulos_usados": [], "artigos": []}


def guardar_historico(historico):
    with open(FICHEIRO_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def escolher_tema_nao_usado(categoria, historico):
    """Escolhe um tema da categoria que ainda não foi usado.
    Se todos já tiverem sido usados, devolve None (categoria esgotada por agora)."""
    candidatos = [
        t for t in TEMAS_POR_CATEGORIA.get(categoria, [])
        if t not in historico["temas_usados"]
    ]
    if not candidatos:
        return None
    return random.choice(candidatos)


def titulo_ja_existe(titulo, historico):
    titulo_normalizado = titulo.strip().lower()
    return any(
        titulo_normalizado == t.strip().lower()
        for t in historico["titulos_usados"]
    )


# ==========================================
# GERAÇÃO DE CONTEÚDO
# ==========================================
def gerar_conteudo_ia(tema, historico, categoria):
    titulos_recentes = historico["titulos_usados"][-30:]  # últimos 30 para não rebentar o prompt
    lista_titulos = "\n".join(f"- {t}" for t in titulos_recentes) or "(nenhum ainda)"

    prompt_completo = (
        f"{PROMPT_SISTEMA}\n\n"
        f"Categoria: {categoria}\n"
        f"Tema: {tema}\n\n"
        f"Artigos já publicados:\n{lista_titulos}"
    )

    for tentativa in range(1, MAX_TENTATIVAS_IA + 1):
        print(f"A redigir artigo sobre: '{tema}' (tentativa {tentativa}/{MAX_TENTATIVAS_IA})...")
        try:
            resposta = modelo.generate_content(prompt_completo)
            texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
            dados = json.loads(texto_limpo)

            # validação mínima das chaves esperadas
            chaves_obrigatorias = {"titulo", "categoria", "resumo", "description", "geo_region", "texto_artigo"}
            if not chaves_obrigatorias.issubset(dados.keys()):
                print("⚠️ JSON incompleto, a tentar novamente.")
                continue

            if titulo_ja_existe(dados["titulo"], historico):
                print(f"⚠️ Título repetido ('{dados['titulo']}'), a tentar novamente.")
                continue

            n_palavras = len(dados["texto_artigo"].split())
            if n_palavras < LIMITE_PALAVRAS_MIN or n_palavras > LIMITE_PALAVRAS_MAX:
                print(f"⚠️ Artigo com {n_palavras} palavras, fora da faixa {LIMITE_PALAVRAS_MIN}-{LIMITE_PALAVRAS_MAX}. A tentar novamente.")
                continue

            return dados

        except json.JSONDecodeError:
            print("⚠️ A IA não devolveu um JSON válido, a tentar novamente.")
        except Exception as e:
            print(f"⚠️ Erro na chamada à API: {e}. A tentar novamente.")

        time.sleep(5)

    print(f"❌ Desisti do tema '{tema}' após {MAX_TENTATIVAS_IA} tentativas.")
    return None


# ==========================================
# PUBLICAÇÃO NO SITE
# ==========================================
def gerar_slug_unico(titulo):
    base = re.sub(r"[^a-z0-9]+", "-", titulo.lower().strip()).strip("-")
    caminho = os.path.join(PASTA_BLOG, f"{base}.mdx")
    if not os.path.exists(caminho):
        return base, caminho
    # se o slug já existir no disco (raro, mas possível), adiciona um sufixo curto
    sufixo = hashlib.md5(titulo.encode("utf-8")).hexdigest()[:6]
    base_unico = f"{base}-{sufixo}"
    return base_unico, os.path.join(PASTA_BLOG, f"{base_unico}.mdx")


def publicar_noticia_no_site(dados_ia, url_imagem):
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    slug, caminho_ficheiro = gerar_slug_unico(dados_ia["titulo"])

    # Blindagem para a Netlify: substitui aspas duplas acidentais por aspas simples
    titulo_limpo = dados_ia["titulo"].replace('"', "'")
    desc_limpa = dados_ia["description"].replace('"', "'")
    resumo_limpo = dados_ia["resumo"].replace('"', "'")

    texto_com_anuncio = dados_ia["texto_artigo"]

    if INSERIR_BLOCO_ADSENSE:
        bloco_adsense = """
<div style="background: #e2e8f0; padding: 2rem; text-align: center; margin: 2rem 0; font-weight: bold; color: #475569; border-radius: 8px;">
  💰 Espaço para o Bloco de Anúncio AdSense 💰
</div>
"""
        paragrafos = texto_com_anuncio.split("\n\n")
        meio = len(paragrafos) // 2
        paragrafos.insert(meio, bloco_adsense)
        texto_com_anuncio = "\n\n".join(paragrafos)

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
    return slug


# ==========================================
# IMAGENS POR CATEGORIA (fallback automático)
# Se quiseres uma imagem específica por tema, usa o dicionário IMAGENS_POR_TEMA.
# ==========================================
IMAGENS_POR_CATEGORIA = {
    "INSS": "/imagens/aposentado-inss.webp",
    "FGTS": "/imagens/fgts-generico.webp",
    "Trabalho CLT": "/imagens/carteira-trabalho.webp",
}

IMAGENS_POR_TEMA = {
    "Governo anuncia mudanças no teto do seguro-desemprego": "/imagens/seguro-desemprego.webp",
}


def obter_imagem(tema, categoria):
    return IMAGENS_POR_TEMA.get(tema, IMAGENS_POR_CATEGORIA.get(categoria, "/imagens/generico.webp"))


# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================
def main():
    historico = carregar_historico()
    categorias = list(TEMAS_POR_CATEGORIA.keys())
    random.shuffle(categorias)  # varia a ordem das categorias a cada execução

    artigos_gerados = 0
    tentativas_globais = 0
    max_tentativas_globais = len(categorias) * 5  # evita loop infinito se tudo estiver esgotado

    while artigos_gerados < ARTIGOS_POR_EXECUCAO and tentativas_globais < max_tentativas_globais:
        for categoria in categorias:
            if artigos_gerados >= ARTIGOS_POR_EXECUCAO:
                break

            tema = escolher_tema_nao_usado(categoria, historico)
            tentativas_globais += 1

            if tema is None:
                print(f"ℹ️ Todos os temas de '{categoria}' já foram usados. A saltar categoria.")
                continue

            dados = gerar_conteudo_ia(tema, historico, categoria)
            time.sleep(PAUSA_ENTRE_CHAMADAS)

            if dados:
                url_imagem = obter_imagem(tema, categoria)
                slug = publicar_noticia_no_site(dados, url_imagem)

                # atualiza e guarda o histórico imediatamente (não perde progresso se o script falhar depois)
                historico["temas_usados"].append(tema)
                historico["titulos_usados"].append(dados["titulo"])
                historico["artigos"].append({
                    "tema": tema,
                    "categoria": categoria,
                    "titulo": dados["titulo"],
                    "slug": slug,
                    "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                guardar_historico(historico)
                artigos_gerados += 1

    print(f"\n🏁 Concluído: {artigos_gerados} artigo(s) gerado(s) nesta execução.")
    if artigos_gerados < ARTIGOS_POR_EXECUCAO:
        print("ℹ️ Não foi possível gerar todos os artigos pedidos (temas esgotados ou falhas da IA).")
        print("   Adiciona mais temas às listas em TEMAS_POR_CATEGORIA para continuar a gerar conteúdo novo.")


if __name__ == "__main__":
    main()