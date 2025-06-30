
# 📈 S&P 500 Golden/Death Cross Scanner (SMA/EMA)

Ce projet est un dashboard Streamlit pour scanner les titres du S&P 500 et détecter ceux proches de réaliser un **golden cross** (MA50 croisant au-dessus de MA200) ou un **death cross** (MA50 croisant en-dessous de MA200), en choisissant entre **SMA** et **EMA**.

## ✅ Fonctionnalités
- Analyse tous les tickers du S&P 500
- Sélection du type de moyenne mobile (SMA ou EMA) depuis l'interface
- Configuration du seuil d'écart (%) pour signaler un croisement imminent
- Tableau interactif avec tickers détectés
- Graphiques détaillés MA50/MA200 pour chaque titre sélectionné

## 🚀 Lancer en local
1. Cloner ce repo ou télécharger les fichiers.
2. Installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Lancer l'application Streamlit :
   ```bash
   streamlit run golden_cross.py
   ```

## 🌐 Déploiement sur Streamlit Cloud
- Crée un repo GitHub avec ces fichiers (`golden_cross.py`, `requirements.txt`, `README.md`).
- Va sur [streamlit.io/cloud](https://streamlit.io/cloud) et connecte ton compte GitHub.
- Sélectionne ton repo et branche, puis clique sur **Deploy**.
- Ton dashboard sera accessible publiquement en ligne.

## 📄 Fichiers
- `golden_cross.py` : le script principal Streamlit
- `requirements.txt` : les dépendances nécessaires
- `README.md` : ce guide

## 📝 A propos
Développé pour l'analyse technique avancée des moyennes mobiles sur le S&P 500.
