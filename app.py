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
API_URL_SUMMARIZATION = "https://api-inference.huggingface.co/models/Falconsai/text_summarization"
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

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_resumo_com_ia(texto_noticia):
    print("🤖 Conectando com a IA da Hugging Face para gerar resumo...")
    try:
        payload = {"inputs": texto_noticia[:1024], "parameters": {"min_length": 20, "max_length": 50}}
        response = requests.post(API_URL_SUMMARIZATION, headers=HEADERS_HF, json=payload)
        response.raise_for_status()
        resultado = response.json()
        resumo = resultado[0]['summary_text']
        print("✅ Resumo gerado pela IA com sucesso!")
        return resumo
    except Exception as e:
        print(f"❌ Erro na IA da Hugging Face: {e}")
        return None

def criar_imagem_post(url_imagem, titulo_post):
    print(f"🎨 Começando a criação da imagem do post...")
    try:
        response_img = requests.get(url_imagem, stream=True)
        response_img.raise_for_status()
        img_bytes = io.BytesIO(response_img.content)
        imagem_noticia = Image.open(img_bytes).convert("RGBA")
        
        fundo = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), (255, 255, 255, 255))
        
        imagem_noticia.thumbnail((1080, 800))
        pos_x = (IMG_WIDTH - imagem_noticia.width) // 2
        fundo.paste(imagem_noticia, (pos_x, 0), imagem_noticia)
        
        draw = ImageDraw.Draw(fundo)
        try: fonte = ImageFont.truetype("arialbd.ttf", 70)
        except IOError: fonte = ImageFont.load_default()
        
        linhas_texto = textwrap.wrap(titulo_post, width=30)
        texto_junto = "\n".join(linhas_texto)
        
        draw.text((540, 940), texto_junto, font=fonte, fill=(0,0,0,255), anchor="ms", align="center")
        
        buffer_saida = io.BytesIO()
        fundo.save(buffer_saida, format='PNG')
        print(f"✅ Imagem do post criada com sucesso!")
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
        print("⚠️ Credenciais da API do Meta não configuradas. Pulando publicação.")
        return "Publicação simulada."
    try:
        url_container = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ID}/media"
        params_container = {'image_url': url_imagem, 'caption': legenda, 'access_token': META_API_TOKEN}
        response_container = requests.post(url_container, params=params_container)
        response_container.raise_for_status()
        id_criacao = response_container.json()['id']
        
        url_publicacao = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ID}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': META_API_TOKEN}
        response_publicacao = requests.post(url_publicacao, params=params_publicacao)
        response_publicacao.raise_for_status()
        
        print("✅ Post publicado no Instagram com sucesso!")
        return "Publicado com sucesso no Instagram."
    except Exception as e:
        print(f"❌ Erro ao publicar no Instagram: {e}")
        return None

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
        if not all([titulo_noticia, url_imagem_destaque]):
            raise ValueError("Dados essenciais faltando.")
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro", "mensagem": "Payload do webhook com formato inválido."}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    
    texto_noticia = BeautifulSoup(html_content, 'html.parser').get_text(separator='\n', strip=True)
    print("✅ Texto da notícia extraído com sucesso.")

    resumo_ia = gerar_resumo_com_ia(texto_noticia)
    if not resumo_ia: return jsonify({"status": "erro", "mensagem": "Falha na IA."}), 500
    
    imagem_gerada_bytes = criar_imagem_post(url_imagem_destaque, titulo_noticia)
    if not imagem_gerada_bytes: return jsonify({"status": "erro", "mensagem": "Falha na criação da imagem."}), 500
    
    nome_do_arquivo = f"post_{dados_wp.get('post_id', 'post_sem_id')}.png"
    link_wp = upload_para_wordpress(imagem_gerada_bytes, nome_do_arquivo)
    if not link_wp: return jsonify({"status": "erro", "mensagem": "Falha no upload para o WordPress."}), 500

    legenda_final = f"{titulo_noticia}\n\n{resumo_ia}\n\n#noticias #brasil #jornalismo"
    status_publicacao = publicar_no_instagram(link_wp, legenda_final)

    if status_publicacao:
        print(f"✅ Automação concluída! Status: {status_publicacao}")
        return jsonify({"status": "sucesso"}), 200
    else:
        return jsonify({"status": "erro", "mensagem": "Falha ao publicar no Instagram."}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação iniciada! Método: Upload para WordPress.")
    app.run(host='0.0.0.0', port=5001, debug=True)