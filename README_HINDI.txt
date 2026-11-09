ZEESHAN AMANAH AI - ONLINE HOSTING FILES

GitHub par app.py, requirements.txt aur render.yaml upload karni hain.
.env aur Gemini API key GitHub par upload NAHI karni.
Render Dashboard > Environment Variables mein GEMINI_API_KEY set karni hai.
Public mobile visitors ki chat history save/share nahi hoti.

Render Build Command: pip install -r requirements.txt
Render Start Command: gunicorn app:web_app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
