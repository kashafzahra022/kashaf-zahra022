# AddiComp Research Hub

AddiComp Research Hub is a Streamlit app to extract and analyze metadata from research PDFs (title, authors, year, keywords, abstract). It saves data to SQLite and shows interactive charts for authors, years and topics.

## Run locally

```bash
# create venv (optional)
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Deploy (recommended: Streamlit Community Cloud)

1. Push this repo to GitHub.
2. Visit https://share.streamlit.io and connect your GitHub repo.
3. Set the main file to `app.py` and deploy.

Alternative: Render / Heroku - the included `Procfile` starts Streamlit with the correct port.
