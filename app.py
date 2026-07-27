# -*- coding: utf-8 -*-
"""Papounapp — visualiser les aversions alimentaires de la famille et des amis.

Lancement local :  streamlit run app.py
Les données sont stockées dans data.csv (une ligne = une personne + un aliment
qu'elle n'aime pas). Ce format correspond exactement à la future Google Sheet,
seules les fonctions charger_donnees / sauvegarder_donnees changeront.
"""

from pathlib import Path

import pandas as pd
import streamlit as st
from pyvis.network import Network

DATA_FILE = Path(__file__).parent / "data.csv"
COL_NOM = "Nom"
COL_ALIMENT = "Aliment"

COULEUR_PERSONNE = "#4e79a7"
COULEUR_ALIMENT = "#f28e2b"


# ---------------------------------------------------------------------------
# Stockage (à remplacer plus tard par la Google Sheet)
# ---------------------------------------------------------------------------

def charger_donnees() -> pd.DataFrame:
    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE, dtype=str).fillna("")
        df = df[(df[COL_NOM] != "") & (df[COL_ALIMENT] != "")]
        return df
    return pd.DataFrame(columns=[COL_NOM, COL_ALIMENT])


def sauvegarder_donnees(df: pd.DataFrame) -> None:
    df = df.sort_values([COL_NOM, COL_ALIMENT]).reset_index(drop=True)
    df.to_csv(DATA_FILE, index=False)


def normaliser(texte: str) -> str:
    """Évite les doublons du type 'pommes' / 'Pommes '."""
    return texte.strip().capitalize()


def normaliser_nom(texte: str) -> str:
    """'jean dupont' -> 'Jean Dupont'."""
    return " ".join(mot.capitalize() for mot in texte.split())


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
noms_existants = sorted(df[COL_NOM].unique())
aliments_existants = sorted(df[COL_ALIMENT].unique())

onglet_reseau, onglet_ajout, onglet_retrait = st.tabs(
    ["🕸️ Réseau des aversions", "➕ Ajouter", "➖ Retirer"]
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
