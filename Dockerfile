# EJQI Suite — Hugging Face Space (Docker SDK)
#
# 허깅페이스가 Streamlit을 네이티브 SDK에서 제외했으므로(현재 gradio·docker·static만 허용)
# Docker로 감싸서 실행한다. 동작은 Streamlit 그대로다.
FROM python:3.11-slim

# HF Space는 uid 1000 사용자로 실행하는 것을 권장한다 (쓰기 가능한 홈 디렉터리 확보)
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

WORKDIR $HOME/app

COPY --chown=user requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860

CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", "--server.address=0.0.0.0", \
     "--server.enableCORS=false", "--server.enableXsrfProtection=true"]
