import streamlit as st
import numpy as np
import pandas as pd
import gpxpy
from google.cloud import firestore

# Authenticate to Firestore with the JSON account key.
db = firestore.Client.from_service_account_json(".streamlit/firebase-hafr-key.json")

st.header('🥾 🪂')

'Welcome to the site of'
st.title('Hike and Fly Records')

uploaded_file = st.file_uploader("Choose your tracklog file",
                                 type = 'gpx')
if uploaded_file is not None:

    gpx = gpxpy.parse(uploaded_file)

    # Convert to a dataframe one point at a time.
    points = []
    for segment in gpx.tracks[0].segments:
        for p in segment.points:
            points.append({
                'time': p.time,
                'latitude': p.latitude,
                'longitude': p.longitude,
                'elevation': p.elevation,
            })
    df = pd.DataFrame.from_records(points)

    st.map(df)

#this not yet works
    ref_uploads = db.collection("uploads").document("test")
    ref_uploads.set({
        "when": 'now',
        "what": 'gpx file'
    })