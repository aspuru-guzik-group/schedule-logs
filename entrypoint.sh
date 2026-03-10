#!/bin/sh
# Merge all secrets/*.toml files into .streamlit/secrets.toml
# shared.toml goes first (top-level keys must come before [sections])
mkdir -p .streamlit
> .streamlit/secrets.toml
[ -f secrets/shared.toml ] && cat secrets/shared.toml >> .streamlit/secrets.toml && echo "" >> .streamlit/secrets.toml
for f in secrets/*.toml; do
  [ "$f" = "secrets/shared.toml" ] && continue
  [ -f "$f" ] && cat "$f" >> .streamlit/secrets.toml && echo "" >> .streamlit/secrets.toml
done
exec streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false
