# ==============================================================================
# BLOCO 1: IMPORTAÇÕES
# ==============================================================================
import os
import io
import json
import requests
import textwrap
import numpy as np
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import imageio
from base64 import b64encode

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# Configs da IA
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
API_URL_INSTRUCT = "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1"
HEADERS_HF = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}

# Configs da Imagem
IMG_WIDTH, IMG_HEIGHT = 1080, 1080

# Configs do WordPress
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}

# Configs da API do Meta (Facebook/Instagram)
META_API_TOKEN = os.getenv('META_API_TOKEN')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID') # Nova variável

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_conteudo_com_ia(titulo, texto_noticia):
    print("🤖 Conectando com a IA para gerar conteúdo completo...")
    prompt = f"""
    Aja como um jornalista de mídias sociais para um portal de notícias. Crie uma legenda para um post.
    Baseado no título e no conteúdo da notícia, crie o seguinte em formato JSON:
    1. "legenda": Um texto curto com 2 ou 3 parágrafos pequenos, terminando com 'Leia a matéria completa no nosso site. Link na bio!'.
    2. "hashtags": Uma string única contendo exatamente 5 hashtags relevantes em português.
    Título: "{titulo}"
    Conteúdo: "{texto_noticia[:1500]}"
    """
    try:
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 250}}
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
    print(f"🎨 Começando a criação da imagem com o novo design...")
    try:
        response_img = requests.get(url_imagem, stream=True); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        response_logo = requests.get(url_logo, stream=True); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")
        
        cor_fundo = "#051d40"
        fundo = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo)
        draw = ImageDraw.Draw(fundo)
        fonte_titulo = ImageFont.truetype("Anton-Regular.ttf", 90)
        fonte_cta = ImageFont.truetype("Anton-Regular.ttf", 60)
        fonte_site = ImageFont.truetype("Anton-Regular.ttf", 35)

        img_w, img_h = 980, 551
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h))
        pos_img_x = (IMG_WIDTH - img_w) // 2
        fundo.paste(imagem_noticia_resized, (pos_img_x, 50))
        
        logo.thumbnail((180, 180))
        fundo.paste(logo, (pos_img_x + 20, 50 + 20), logo)
        
        linhas_texto = textwrap.wrap(titulo_post, width=22)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, 650), texto_junto, font=fonte_titulo, fill=(255,255,255,255), anchor="ma", align="center")
        
        draw.text((IMG_WIDTH / 2, 950), "LEIA MAIS", font=fonte_cta, fill="#FF0000", anchor="ms", align="center")
        draw.text((IMG_WIDTH / 2, 1000), "jornalvozdolitoral.com", font=fonte_site, fill=(255,255,255,255), anchor="ms", align="center")
        
        buffer_saida = io.BytesIO()
        fundo.save(buffer_saida, format='PNG')
        print(f"✅ Imagem com novo design criada com sucesso!")
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ Erro ao criar imagem com Pillow: {e}")
        return None

def upload_para_wordpress(bytes_imagem, nome_arquivo):
    print(f"⬆️ Fazendo upload de '{nome_arquivo}' para o WordPress...")
    try:
        url_wp_media = f"{WP_URL}/wp-json/wp/v2/media"
        headers_upload = HEADERS_WP.copy()
        headers_upload['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
        headers_upload['Content-Type'] = 'image/png'
        response = requests.post(url_wp_media, headers=headers_upload, data=bytes_imagem)
        response.raise_for_status()
        link_imagem_publica = response.json()['source_url']
        print(f"✅ Imagem salva na Biblioteca de Mídia! Link: {link_imagem_publica}")
        return link_imagem_publica
    except Exception as e:
        print(f"❌ Erro ao fazer upload para o WordPress: {e}")
        return None

def publicar_no_instagram(url_imagem, legenda):
    print("📤 Publicando no Instagram...")
    if not all([META_API_TOKEN, INSTAGRAM_ID]):
        print("⚠️ Credenciais do Instagram não configuradas. Pulando publicação.")
        return "Publicação no Instagram pulada."
    try:
        url_container = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media"
        params_container = {'image_url': url_imagem, 'caption': legenda, 'access_token': META_API_TOKEN}
        r_container = requests.post(url_container, params=params_container); r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        
        url_publicacao = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': META_API_TOKEN}
        r_publish = requests.post(url_publicacao, params=params_publicacao); r_publish.raise_for_status()
        
        print("✅ Post publicado no Instagram com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar no Instagram: {e}")
        return False

# --- NOVA FUNÇÃO ---
def publicar_no_facebook(url_imagem, legenda):
    print("📤 Publicando no Facebook...")
    if not all([META_API_TOKEN, FACEBOOK_PAGE_ID]):
        print("⚠️ Credenciais do Facebook não configuradas. Pulando publicação.")
        return "Publicação no Facebook pulada."
    try:
        url_post_foto = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/photos"
        params = {'url': url_imagem, 'caption': legenda, 'access_token': META_API_TOKEN}
        r = requests.post(url_post_foto, params=params); r.raise_for_status()
        
        print("✅ Post publicado na Página do Facebook com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar no Facebook: {e}")
        return False

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    print("\n\n🔔 Webhook recebido do WordPress!")
    dados_brutos = request.json
    dados_wp = dados_brutos[0] if isinstance(dados_brutos, list) and dados_brutos else dados_brutos
    
    try:
        titulo_noticia = dados_wp.get('post', {}).get('post_title')
        html_content = dados_wp.get('post', {}).get('post_content')
        if not html_content: raise ValueError("Conteúdo do post não encontrado.")
        
        soup_img = BeautifulSoup(html_content, 'html.parser')
        primeira_imagem_tag = soup_img.find('img')
        if not primeira_imagem_tag: raise ValueError("Nenhuma tag <img> encontrada.")
        
        url_imagem_destaque = primeira_imagem_tag.get('src')
        url_logo = "http://jornalvozdolitoral.com/wp-content/uploads/2025/08/Redondo.png"
        
        if not all([titulo_noticia, url_imagem_destaque]):
            raise ValueError("Dados essenciais faltando.")
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro", "mensagem": "Payload do webhook com formato inválido."}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    
    texto_noticia = BeautifulSoup(html_content, 'html.parser').get_text(separator='\n', strip=True)
    print("✅ Texto da notícia extraído com sucesso.")

    conteudo_ia = gerar_conteudo_com_ia(titulo_noticia, texto_noticia)
    if not conteudo_ia: return jsonify({"status": "erro", "mensagem": "Falha na IA."}), 500
    
    imagem_gerada_bytes = criar_imagem_post(url_imagem_destaque, titulo_noticia, url_logo)
    if not imagem_gerada_bytes: return jsonify({"status": "erro", "mensagem": "Falha na criação da imagem."}), 500
    
    nome_do_arquivo = f"post_{dados_wp.get('post_id', 'post_sem_id')}.png"
    link_wp = upload_para_wordpress(imagem_gerada_bytes, nome_do_arquivo)
    if not link_wp: return jsonify({"status": "erro", "mensagem": "Falha no upload para o WordPress."}), 500

    legenda_final = f"{conteudo_ia['legenda']}\n\n{conteudo_ia['hashtags']}"
    
    # --- CHAMANDO AS DUAS PUBLICAÇÕES ---
    sucesso_ig = publicar_no_instagram(link_wp, legenda_final)
    sucesso_fb = publicar_no_facebook(link_wp, legenda_final)

    if sucesso_ig or sucesso_fb:
        print("✅ Automação concluída!")
        return jsonify({"status": "sucesso"}), 200
    else:
        return jsonify({"status": "erro", "mensagem": "Falha ao publicar em todas as redes."}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação v3.0 iniciada! Design + IA + Multi-rede.")
    app.run(host='0.0.0.0', port=5001, debug=True)