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
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import imageio # A estrela da nossa nova solução

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    print(f"❌ ERRO GRAVE: Não foi possível configurar a API do Gemini. Verifique sua chave no arquivo .env. Erro: {e}")

# Constantes para o vídeo
REELS_WIDTH = 1080
REELS_HEIGHT = 1920
VIDEO_DURATION = 8
FPS = 24 # Frames por segundo

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_conteudo_com_ia(texto_noticia):
    print("🤖 Conectando com a IA para gerar conteúdo...")
    try:
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        prompt = f"""
        Aja como um editor de social media para um portal de notícias brasileiro.
        Baseado na notícia abaixo, gere o seguinte conteúdo para um Reels do Instagram no formato JSON:
        1.  "titulo_video": Um título muito curto e impactante para aparecer no vídeo (máximo 10 palavras).
        2.  "legenda": Uma legenda para o post, resumindo a notícia em 2-3 frases e terminando com "Leia a matéria completa no link da bio.".
        3.  "hashtags": Uma string única contendo de 5 a 7 hashtags relevantes separadas por espaço (ex: "#noticia #brasil #politica").

        Notícia:
        {texto_noticia[:4000]}
        """
        response = model.generate_content(prompt)
        json_response_text = response.text.replace("```json", "").replace("```", "").strip()
        conteudo_gerado = json.loads(json_response_text)
        print("✅ Conteúdo gerado pela IA com sucesso!")
        return conteudo_gerado
    except Exception as e:
        print(f"❌ Erro na IA: {e}")
        return None

def criar_video_com_pillow(url_imagem, titulo_video, nome_arquivo_saida="reels_gerado.mp4"):
    print(f"🎬 Começando a criação do vídeo com o novo método (Pillow + Imageio)...")
    try:
        # 1. Baixar a imagem da notícia
        response_img = requests.get(url_imagem, stream=True)
        response_img.raise_for_status()
        img_bytes = io.BytesIO(response_img.content)
        imagem_noticia = Image.open(img_bytes).convert("RGBA")

        # 2. Criar o fundo preto do Reels
        fundo = Image.new('RGBA', (REELS_WIDTH, REELS_HEIGHT), (0, 0, 0, 255))

        # 3. Redimensionar e colar a imagem da notícia no fundo
        imagem_noticia.thumbnail((REELS_WIDTH * 0.9, REELS_HEIGHT * 0.9)) # Redimensiona mantendo proporção
        pos_x = (REELS_WIDTH - imagem_noticia.width) // 2
        pos_y = (REELS_HEIGHT - imagem_noticia.height) // 2
        fundo.paste(imagem_noticia, (pos_x, pos_y), imagem_noticia)

        # 4. Adicionar o texto sobre a imagem
        draw = ImageDraw.Draw(fundo)
        try:
            # Tenta usar uma fonte comum. Se não encontrar, usa a padrão.
            fonte = ImageFont.truetype("arialbd.ttf", 90)
        except IOError:
            print("⚠️ Fonte Arial Bold não encontrada, usando fonte padrão.")
            fonte = ImageFont.load_default()

        # Quebra o texto em várias linhas se for muito longo
        linhas_texto = textwrap.wrap(titulo_video.upper(), width=20)
        texto_junto = "\n".join(linhas_texto)
        
        # Desenha o texto com sombra
        x, y = REELS_WIDTH / 2, REELS_HEIGHT * 0.8
        # Sombra preta
        draw.text((x+5, y+5), texto_junto, font=fonte, fill=(0,0,0,255), anchor="ms", align="center")
        # Texto branco
        draw.text((x, y), texto_junto, font=fonte, fill=(255,255,255,255), anchor="ms", align="center")

        # 5. Criar o vídeo a partir da imagem final
        # Converte a imagem final do Pillow para um formato que o imageio entende (numpy array)
        frame_final = np.array(fundo)
        
        # Cria uma lista de frames idênticos para compor o vídeo
        frames = [frame_final for _ in range(FPS * VIDEO_DURATION)]

        # Salva a sequência de frames como um vídeo MP4
        imageio.mimsave(nome_arquivo_saida, frames, fps=FPS, codec='libx264')

        print(f"✅ Vídeo '{nome_arquivo_saida}' salvo com sucesso com o novo método!")
        return nome_arquivo_saida
    except Exception as e:
        print(f"❌ Erro ao criar vídeo com Pillow/Imageio: {e}")
        return None

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    # ... (O CÓDIGO DESTE BLOCO CONTINUA EXATAMENTE O MESMO) ...
    print("\n\n🔔 Webhook recebido do WordPress!")
    dados_wp = request.json
    try:
        url_noticia = dados_wp.get('post', {}).get('permalink')
        titulo_noticia = dados_wp.get('post', {}).get('post_title')
        url_imagem_destaque = dados_wp.get('post_meta', {}).get('thumbnail') 
        
        if not all([url_noticia, titulo_noticia, url_imagem_destaque]):
            print("❌ Erro: Dados essenciais faltando no webhook.")
            return jsonify({"status": "erro", "mensagem": "Payload do webhook inválido."}), 400
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro", "mensagem": "Payload do webhook com formato inesperado."}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    print(f"🖼️ Imagem: {url_imagem_destaque}")

    try:
        print(f"💻 Lendo o conteúdo de: {url_noticia}")
        response_page = requests.get(url_noticia)
        soup = BeautifulSoup(response_page.content, 'html.parser')
        corpo_artigo = soup.find('div', class_='entry-content') 
        texto_noticia = corpo_artigo.get_text(separator='\n', strip=True)
        print("✅ Texto da notícia extraído com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao ler a página da notícia: {e}")
        return jsonify({"status": "erro", "mensagem": "Não foi possível ler a URL."}), 400

    conteudo_ia = gerar_conteudo_com_ia(texto_noticia)
    if not conteudo_ia:
        return jsonify({"status": "erro", "mensagem": "Falha na IA."}), 500
    
    # AQUI CHAMAMOS A NOSSA NOVA FUNÇÃO DE CRIAR VÍDEO
    caminho_video_final = criar_video_com_pillow(url_imagem_destaque, conteudo_ia['titulo_video'])
    if not caminho_video_final:
        return jsonify({"status": "erro", "mensagem": "Falha na criação do vídeo."}), 500

    legenda_final = f"{conteudo_ia['legenda']}\n.\n.\n.\n{conteudo_ia['hashtags']}"
    print("📤 Simulando publicação do Reel...")
    print(f"   -> Vídeo a ser publicado: {caminho_video_final}")
    print(f"   -> Legenda do post: {legenda_final}")
    print("✅ Automação concluída com sucesso para esta notícia!")
    return jsonify({"status": "sucesso"}), 200

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação iniciada com o método alternativo!")
    app.run(host='0.0.0.0', port=5001, debug=True)