# -*- coding: utf-8 -*-
"""Papounapp — visualiser les aversions alimentaires de la famille et des amis.

Lancement local :  streamlit run app.py
Les données sont stockées dans data.csv (une ligne = une personne + un aliment
qu'elle n'aime pas). Ce format correspond exactement à la future Google Sheet,
seules les fonctions charger_donnees / sauvegarder_donnees changeront.
"""

import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st
from pyvis.network import Network
from streamlit_gsheets import GSheetsConnection

DATA_FILE = Path(__file__).parent / "data.csv"
RECETTES_FILE = Path(__file__).parent / "recettes.csv"
COL_NOM = "Nom"
COL_ALIMENT = "Aliment"
COLONNES_RECETTES = ["Recette", "Type", "Ingrédients", "Lien"]

COULEUR_PERSONNE = "#4e79a7"
COULEUR_ALIMENT = "#f28e2b"


# ---------------------------------------------------------------------------
# Stockage : Google Sheet si configurée (secrets), sinon CSV local
# ---------------------------------------------------------------------------

FEUILLE = "aversions"  # nom de l'onglet dans la Google Sheet
FEUILLE_RECETTES = "recettes"


def utilise_gsheet() -> bool:
    try:
        return "gsheets" in st.secrets.get("connections", {})
    except Exception:
        return False


def _nettoyer(df: pd.DataFrame) -> pd.DataFrame:
    df = df[[COL_NOM, COL_ALIMENT]].fillna("").astype(str)
    df[COL_NOM] = df[COL_NOM].str.strip()
    df[COL_ALIMENT] = df[COL_ALIMENT].str.strip()
    return df[(df[COL_NOM] != "") & (df[COL_ALIMENT] != "")]


def charger_donnees() -> pd.DataFrame:
    if utilise_gsheet():
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet=FEUILLE, ttl=0)
        if df is None or df.empty:
            return pd.DataFrame(columns=[COL_NOM, COL_ALIMENT])
        return _nettoyer(df)
    if DATA_FILE.exists():
        return _nettoyer(pd.read_csv(DATA_FILE, dtype=str))
    return pd.DataFrame(columns=[COL_NOM, COL_ALIMENT])


def charger_recettes() -> pd.DataFrame:
    df = None
    if utilise_gsheet():
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet=FEUILLE_RECETTES, ttl=0)
        except Exception:
            df = None  # l'onglet "recettes" n'existe pas (encore) dans la Sheet
    elif RECETTES_FILE.exists():
        df = pd.read_csv(RECETTES_FILE, dtype=str)
    if df is None or df.empty:
        return pd.DataFrame(columns=COLONNES_RECETTES)
    for col in COLONNES_RECETTES:
        if col not in df.columns:
            df[col] = ""
    df = df[COLONNES_RECETTES].fillna("").astype(str)
    return df[df["Recette"].str.strip() != ""]


def sauvegarder_donnees(df: pd.DataFrame) -> None:
    df = df.sort_values([COL_NOM, COL_ALIMENT]).reset_index(drop=True)
    if utilise_gsheet():
        conn = st.connection("gsheets", type=GSheetsConnection)
        conn.update(worksheet=FEUILLE, data=df)
    else:
        df.to_csv(DATA_FILE, index=False)


def sauvegarder_recettes(df: pd.DataFrame) -> None:
    df = df[COLONNES_RECETTES].sort_values(["Type", "Recette"]).reset_index(drop=True)
    if utilise_gsheet():
        conn = st.connection("gsheets", type=GSheetsConnection)
        try:
            conn.update(worksheet=FEUILLE_RECETTES, data=df)
        except Exception:
            conn.create(worksheet=FEUILLE_RECETTES, data=df)
    else:
        df.to_csv(RECETTES_FILE, index=False)


def normaliser(texte: str) -> str:
    """Évite les doublons du type 'pommes' / 'Pommes '."""
    return texte.strip().capitalize()


def normaliser_nom(texte: str) -> str:
    """'jean dupont' -> 'Jean Dupont'."""
    return " ".join(mot.capitalize() for mot in texte.split())


def cle_aliment(texte: str) -> str:
    """Clé de comparaison tolérante : 'Œufs' et 'oeuf' donnent la même clé.

    On compare des ingrédients entiers (jamais des sous-chaînes), donc
    'Pommes' ne bloque pas 'Pommes de terre'.
    """
    t = texte.strip().lower().replace("œ", "oe")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return t[:-1] if t.endswith("s") else t


def recettes_compatibles(recettes: pd.DataFrame, aliments_interdits: set) -> pd.DataFrame:
    interdits = {cle_aliment(a) for a in aliments_interdits}

    def ok(ingredients: str) -> bool:
        return not any(cle_aliment(i) in interdits for i in ingredients.split(",") if i.strip())

    return recettes[recettes["Ingrédients"].apply(ok)]


# ---------------------------------------------------------------------------
# Réseau interactif
# ---------------------------------------------------------------------------

def construire_reseau(df: pd.DataFrame) -> str:
    net = Network(
        height="620px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#333333",
        cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-4000, central_gravity=0.3, spring_length=120)

    compte_aliments = df.groupby(COL_ALIMENT)[COL_NOM].agg(list)

    for nom in sorted(df[COL_NOM].unique()):
        aliments = sorted(df.loc[df[COL_NOM] == nom, COL_ALIMENT])
        net.add_node(
            f"p::{nom}",
            label=nom,
            color=COULEUR_PERSONNE,
            shape="dot",
            size=25,
            title=f"{nom} n'aime pas : {', '.join(aliments)}",
        )

    for aliment, personnes in compte_aliments.items():
        n = len(personnes)
        net.add_node(
            f"a::{aliment}",
            label=aliment,
            color=COULEUR_ALIMENT,
            shape="dot",
            size=12 + 6 * n,
            title=f"{aliment} — détesté par {n} personne(s) : {', '.join(sorted(personnes))}",
        )

    for _, ligne in df.iterrows():
        net.add_edge(f"p::{ligne[COL_NOM]}", f"a::{ligne[COL_ALIMENT]}", color="#cccccc")

    return net.generate_html()


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Papounapp", page_icon="🍽️", layout="wide")
st.title("🍽️ Papounapp — les goûts de chacun")

df = charger_donnees()
recettes_df = charger_recettes()
noms_existants = sorted(df[COL_NOM].unique())
aliments_existants = sorted(df[COL_ALIMENT].unique())

# Vocabulaire commun : aliments des aversions + ingrédients des recettes
aliments_connus = set(aliments_existants)
for _ing in recettes_df["Ingrédients"]:
    aliments_connus.update(i.strip() for i in _ing.split(",") if i.strip())
aliments_connus = sorted(aliments_connus)

onglet_reseau, onglet_recettes, onglet_ajout, onglet_retrait = st.tabs(
    ["🕸️ Réseau des aversions", "📖 Recettes", "➕ Ajouter", "➖ Retirer"]
)

# --- Onglet principal : le réseau ------------------------------------------
with onglet_reseau:
    if df.empty:
        st.info("Aucune donnée pour l'instant. Ajoutez des personnes dans l'onglet « Ajouter ».")
    else:
        selection = st.multiselect(
            "Choisissez les personnes à afficher :",
            options=noms_existants,
            default=noms_existants,
        )
        sous_df = df[df[COL_NOM].isin(selection)]
        if sous_df.empty:
            st.warning("Sélectionnez au moins une personne.")
        else:
            st.caption(
                "🔵 personnes — 🟠 aliments détestés (plus le rond est gros, plus il est "
                "détesté). Survolez un point pour les détails, faites glisser pour réorganiser."
            )
            st.iframe(construire_reseau(sous_df), height=640)

            aliments_a_eviter = (
                sous_df.groupby(COL_ALIMENT)[COL_NOM]
                .agg(lambda s: ", ".join(sorted(s)))
                .reset_index()
                .rename(columns={COL_ALIMENT: "Aliment à éviter", COL_NOM: "Détesté par"})
            )
            st.subheader("📋 Aliments à éviter pour ce groupe")
            st.dataframe(aliments_a_eviter, width="stretch", hide_index=True)

            st.subheader("🍲 Suggestions de recettes")
            if recettes_df.empty:
                st.info("Aucune recette enregistrée : ajoutez-en dans l'onglet « Recettes ».")
            else:
                col_e, col_p, col_d, col_btn = st.columns([1, 1, 1, 2])
                categories = []
                if col_e.checkbox("Entrée"):
                    categories.append("Entrée")
                if col_p.checkbox("Plat", value=True):
                    categories.append("Plat")
                if col_d.checkbox("Dessert"):
                    categories.append("Dessert")
                if col_btn.button("🎲 Nouvelle sélection"):
                    st.session_state["graine"] = st.session_state.get("graine", 0) + 1

                if not categories:
                    st.warning("Cochez au moins une catégorie.")
                else:
                    candidates = recettes_df[recettes_df["Type"].isin(categories)]
                    eligibles = recettes_compatibles(candidates, set(sous_df[COL_ALIMENT]))
                    if eligibles.empty:
                        st.warning(
                            "Aucune recette de ces catégories n'est compatible avec ce groupe. "
                            "Essayez d'autres catégories ou ajoutez des recettes."
                        )
                    else:
                        n = min(5, len(eligibles))
                        suggestions = eligibles.sample(
                            n=n, random_state=st.session_state.get("graine", 0)
                        )
                        st.caption(
                            f"{n} suggestion(s) tirée(s) au hasard parmi {len(eligibles)} "
                            f"recette(s) compatibles avec : {', '.join(selection)}."
                        )
                        st.dataframe(
                            suggestions,
                            width="stretch",
                            hide_index=True,
                            column_config={
                                "Lien": st.column_config.LinkColumn(
                                    "Recette complète", display_text="Ouvrir sur Marmiton"
                                ),
                            },
                        )

# --- Onglet recettes --------------------------------------------------------
with onglet_recettes:
    if recettes_df.empty:
        st.info("Aucune recette enregistrée pour l'instant : ajoutez la première ci-dessous !")
    else:
        recettes = recettes_df
        col_recherche, col_type = st.columns([2, 1])
        recherche = col_recherche.text_input(
            "🔍 Rechercher :", placeholder="nom de recette ou ingrédient…"
        )
        types = ["Tous"] + sorted(t for t in recettes["Type"].unique() if t)
        choix_type = col_type.selectbox("Type de plat :", types)

        filtrees = recettes
        if choix_type != "Tous":
            filtrees = filtrees[filtrees["Type"] == choix_type]
        if recherche.strip():
            terme = recherche.strip()
            masque = filtrees["Recette"].str.contains(
                terme, case=False, regex=False
            ) | filtrees["Ingrédients"].str.contains(terme, case=False, regex=False)
            filtrees = filtrees[masque]

        st.caption(f"{len(filtrees)} recette(s) — les liens ouvrent la recette complète sur Marmiton.")
        st.dataframe(
            filtrees,
            width="stretch",
            hide_index=True,
            column_config={
                "Lien": st.column_config.LinkColumn(
                    "Recette complète", display_text="Ouvrir sur Marmiton"
                ),
            },
        )

    st.divider()
    st.subheader("Ajouter une recette")

    nom_recette = st.text_input("Nom de la recette (ex : Gratin de courgettes)")
    type_recette = st.selectbox("Type :", ["Plat", "Entrée", "Dessert"])
    ingredients_choisis = st.multiselect(
        "Ingrédients déjà connus :",
        options=aliments_connus,
        help="Réutilisez les noms existants autant que possible : c'est ce qui permet "
        "de filtrer les recettes selon les aversions de chacun.",
    )
    nouveaux_ingredients = st.text_input(
        "Nouveaux ingrédients, séparés par des virgules (si absents de la liste ci-dessus)"
    )
    lien_recette = st.text_input("Lien vers la recette complète (optionnel)")

    if st.button("Ajouter la recette", type="primary"):
        nom_recette = nom_recette.strip()
        ingredients = [normaliser(i) for i in ingredients_choisis]
        ingredients += [
            normaliser(i) for i in nouveaux_ingredients.split(",") if i.strip()
        ]
        ingredients = sorted(set(ingredients))
        if not nom_recette:
            st.error("Veuillez indiquer le nom de la recette.")
        elif not ingredients:
            st.error("Veuillez indiquer au moins un ingrédient.")
        elif nom_recette.lower() in recettes_df["Recette"].str.lower().values:
            st.error(f"« {nom_recette} » existe déjà dans la liste.")
        else:
            nouvelle = pd.DataFrame(
                [
                    {
                        "Recette": nom_recette,
                        "Type": type_recette,
                        "Ingrédients": ", ".join(ingredients),
                        "Lien": lien_recette.strip(),
                    }
                ]
            )
            sauvegarder_recettes(pd.concat([recettes_df, nouvelle]))
            st.success(f"« {nom_recette} » ({type_recette}) a été ajoutée.")
            st.rerun()

# --- Onglet ajout -----------------------------------------------------------
with onglet_ajout:
    st.subheader("Ajouter une personne ou compléter ses aversions")

    NOUVELLE = "— Nouvelle personne —"
    choix = st.selectbox("Personne :", [NOUVELLE] + noms_existants)
    if choix == NOUVELLE:
        nom = st.text_input("Nom de la nouvelle personne (ex : Jean Dupont)")
    else:
        nom = choix

    aliments_choisis = st.multiselect(
        "Aliments déjà connus qu'il/elle n'aime pas :", options=aliments_existants
    )
    nouveaux_aliments = st.text_input(
        "Autres aliments, séparés par des virgules (ex : pommes, poisson, chou-fleur)"
    )

    if st.button("Ajouter", type="primary"):
        nom = normaliser_nom(nom) if nom else ""
        aliments = [normaliser(a) for a in aliments_choisis]
        aliments += [normaliser(a) for a in nouveaux_aliments.split(",") if a.strip()]
        if not nom:
            st.error("Veuillez indiquer un nom.")
        elif not aliments:
            st.error("Veuillez indiquer au moins un aliment.")
        else:
            ajout = pd.DataFrame({COL_NOM: nom, COL_ALIMENT: sorted(set(aliments))})
            df = (
                pd.concat([df, ajout])
                .drop_duplicates(subset=[COL_NOM, COL_ALIMENT])
                .reset_index(drop=True)
            )
            sauvegarder_donnees(df)
            st.success(f"C'est noté : {nom} n'aime pas {', '.join(sorted(set(aliments)))}.")
            st.rerun()

# --- Onglet retrait ---------------------------------------------------------
with onglet_retrait:
    st.subheader("Retirer des aliments ou une personne")

    if not noms_existants:
        st.info("Aucune personne enregistrée pour l'instant.")
    else:
        nom_retrait = st.selectbox("Personne :", noms_existants, key="nom_retrait")
        aliments_personne = sorted(df.loc[df[COL_NOM] == nom_retrait, COL_ALIMENT])
        a_retirer = st.multiselect(
            f"Aliments à retirer de la liste de {nom_retrait} :", options=aliments_personne
        )
        tout_supprimer = st.checkbox(f"Supprimer complètement {nom_retrait}")

        if st.button("Retirer", type="primary"):
            if tout_supprimer:
                df = df[df[COL_NOM] != nom_retrait]
                message = f"{nom_retrait} a été supprimé(e)."
            elif a_retirer:
                masque = (df[COL_NOM] == nom_retrait) & (df[COL_ALIMENT].isin(a_retirer))
                df = df[~masque]
                message = f"Retiré pour {nom_retrait} : {', '.join(a_retirer)}."
                if df[df[COL_NOM] == nom_retrait].empty:
                    message += f" {nom_retrait} n'avait plus d'aversion, il/elle a été retiré(e)."
            else:
                st.error("Sélectionnez des aliments à retirer, ou cochez la suppression complète.")
                st.stop()
            sauvegarder_donnees(df.reset_index(drop=True))
            st.success(message)
            st.rerun()
