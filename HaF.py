import streamlit as st
import numpy as np
import pandas as pd
import gpxpy
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# Authenticate to firebase with the JSON account key.
if not firebase_admin._apps:
    cred = credentials.Certificate(".streamlit/firebase-hafr-key.json")
    default_app = firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://hafr-e2128-default-rtdb.europe-west1.firebasedatabase.app/'
    })

# create reference to the root of the database
ref = db.reference('/')

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
    d2 = df.to_dict()

    #save to db 
    ref.push(d2)
