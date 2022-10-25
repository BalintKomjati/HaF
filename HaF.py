#%% import libs & config
import pandas as pd
import streamlit as st
import geopandas as gpd
import geopy.distance
import gpxpy
import json
import os
from google.cloud import firestore
from google.oauth2 import service_account
from numpy import mean, min, max
import leafmap.foliumap as leafmap
from folium import Marker, Circle
from folium.plugins import AntPath, MeasureControl
from folium.features import CustomIcon
from string import Template

import haf_module as haf

# Authenticate to Firestore
db = haf.connect_firestore()
db_race = db.collection('races').document('eged')

#%% frontend sidebar
st.set_page_config(layout="wide")

st.sidebar.title("About")

st.sidebar.info(
    """
    Website for Hike-and-fly records.
    """
)

st.sidebar.info(
    """
    App by [Bálint Komjáti](https://balint-komjati.hu)
    """
)

#%% main app
def app():
    #%% frontend headers
    st.subheader('Welcome to the site of')   
    st.title('Hike and Fly Records')    
    st.subheader('⛰️ 🥾 🪂 🏆')
    st.text('')

    #%% create map
    m = haf.create_basis_map()
    startcylinder = haf.get_task_cylinders(db_race,"startcylinder")
    turnpoint = haf.get_task_cylinders(db_race,"turnpoint")
    m = haf.add_task_to_map(m, startcylinder, turnpoint)
    m.fit_bounds(haf.get_task_bounds(startcylinder, turnpoint))

    #%% frontend gpx uploader
    gpx_file = st.file_uploader(label = 'Upload you gpx tracklog for evaluation:', type = 'gpx')

    #%% actions if user uploads gpx file
    if gpx_file is not None:

        #%% read gpx file and add to map
        gpx = gpxpy.parse(gpx_file)
        pdf = haf.gpx_to_df(gpx)
        pdf_to_antpath = pdf[["latitude","longitude"]].values.tolist()
        AntPath(pdf_to_antpath, color='blue', weight=4.5, opacity=.5, fitBounds = True).add_to(m)

        #%% validate user gpx

        pdf = haf.identify_up_and_down_segments(pdf, startcylinder, turnpoint)

        #check if track crosses start and exit cylinders
        if pdf.inside_start.sum() < 1:
            st.error("Tracklog does not cross the start cylinder!")
        if pdf.inside_tp.sum() < 1:
            st.error("Tracklog does not corss the turnpoint!")

        #check if segment up is finished before segment down starts
        if pdf.query("segment_up").idx.max() > pdf.query("segment_down").idx.min():
            st.error('Order of tagging the cylinders is incorrect')


        #%% Extract results info from gpx

        # calculate up and down timedeltas
        time_up   = pdf[pdf['segment_up'  ] == True].time.max() - pdf[pdf['segment_up'  ] == True].time.min()
        time_down = pdf[pdf['segment_down'] == True].time.max() - pdf[pdf['segment_down'] == True].time.min()

        # site info: name, map, elevation, distance, avg grade, elev min max
        # TODO add ranking and climb rate
        df = pd.DataFrame({
            "Athlete" : ["Earl"],
            "Date" : [pdf.time[1].strftime('%Y.%m.%d')],
            "Time up" :   haf.strfdelta(time_up,   '%H:%M:%S'),
            "Time down" : haf.strfdelta(time_down, '%H:%M:%S')
            })
  
        st.dataframe(df, use_container_width = True) 

        m.fit_bounds(haf.get_gpx_bounds(pdf)) #might be more elegant with gdf.total_bounds()

    m.to_streamlit()

app()