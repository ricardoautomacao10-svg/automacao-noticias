# ==============================================================================
# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO
# ==============================================================================
import os
import io
import json
import requests
import textwrap
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode

load_dotenv()
app = Flask(__name__)

# Configs
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
API_URL_INSTRUCT = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
HEADERS_HF = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
IMG_WIDTH, IMG_HEIGHT = 1080, 1080
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
META_API_TOKEN = os.getenv('META_API_TOKEN')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')

# ==============================================================================
# BLOCO 2: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_conteudo_com_ia(titulo, texto_noticia):
    print("🤖 Conectando com a IA (Mistral-7B) para gerar conteúdo completo...")
    prompt = f"""
    [INST] Aja como um jornalista de mídias sociais para um portal de notícias chamado 'Jornal Voz do Litoral'. Sua tarefa é criar uma legenda para um post no Instagram.
    Baseado no título e no conteúdo da notícia abaixo, crie o seguinte em formato JSON, e nada mais:
    1. "legenda": Um texto curto e informativo com 2 ou 3 parágrafos pequenos. O texto deve ser envolvente e terminar com uma chamada para ação como 'Leia a matéria completa em nosso site. Link na bio!'.
    2. "hashtags": Uma string única contendo exatamente 5 hashtags relevantes em português, começando com #.

    Título da Notícia: "{titulo}"
    Conteúdo da Notícia: "{texto_noticia[:1500]}" [/INST]
    """
    try:
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 250, "return_full_text": False}}
        response = requests.post(API_URL_INSTRUCT, headers=HEADERS_HF, json=payload)
        response.raise_for_status()
        resultado_texto = response.json()[0]['generated_text']
        json_str = '{' + resultado_texto.split('{', 1)[-1].rsplit('}', 1)[0] + '}'
        conteudo_gerado = json.loads(json_str)
        print("✅ Conteúdo completo (legenda e hashtags) gerado pela IA!")
        return conteudo_gerado
    except Exception as e:
        print(f"❌ Erro na IA da Hugging Face: {e}")
        return None

def criar_imagem_post(url_imagem, titulo_post, url_logo):
    print(f"🎨 Começando a criação da imagem com o design final...")
    try:
        response_img = requests.get(url_imagem, stream=True); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        response_logo = requests.get(url_logo, stream=True); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")
        cor_fundo = "#051d40"; fundo = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo)
        draw = ImageDraw.Draw(fundo)
        fonte_titulo = ImageFont.truetype("Anton-Regular.ttf", 40)
        fonte_cta = ImageFont.truetype("Anton-Regular.ttf", 32)
        fonte_site = ImageFont.truetype("Anton-Regular.ttf", 28)
        img_w, img_h = 980, 551
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h))
        pos_img_x = (IMG_WIDTH - img_w) // 2
        fundo.paste(imagem_noticia_resized, (pos_img_x, 50))
        logo.thumbnail((180, 180)); fundo.paste(logo, (pos_img_x + 20, 50 + 20), logo)
        linhas_texto = textwrap.wrap(titulo_post, width=50)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, 700), texto_junto, font=fonte_titulo, fill=(255,255,255,255), anchor="ma", align="center")
        draw.text((IMG_WIDTH / 2, 950), "LEIA MAIS", font=fonte_cta, fill="#FF0000", anchor="ms", align="center")
        draw.text((IMG_WIDTH / 2, 1000), "jornalvozdolitoral.com", font=fonte_site, fill=(255,255,255,255), anchor="ms", align="center")
        buffer_saida = io.BytesIO()
        fundo.save(buffer_saida, format='PNG')
        print(f"✅ Imagem com novo design criada com sucesso!")
        return buffer_saida.getvalue