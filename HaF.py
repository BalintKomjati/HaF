import streamlit as st
import numpy as np
import pandas as pd
import gpxpy
from google.cloud import firestore
import json
from google.oauth2 import service_account

key_dict = json.loads(st.secrets["textkey"])
creds = service_account.Credentials.from_service_account_info(key_dict)
db = firestore.Client(credentials=creds, project="hafr-e2128")

'Welcome to the site of'

st.header('⛰️ 🥾 🪂 🏆')

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

    #visualize
    st.map(df)

    #timestamp is not json convertible
    df['time'] = df['time'].astype(str)
    
    #convert to dictionary (only way to upload to firebase)
    d2 = df.to_dict(orient = 'records')

    #save to db  
    doc_ref = db.collection("gpx")
    list(map(lambda x: doc_ref.add(x), d2))