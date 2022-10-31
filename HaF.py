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

    #%% create map and download task results
    df_results = haf.download_task_results(db_race)

    m = haf.create_basis_map()
    startcylinder = haf.download_task_cylinders(db_race,"startcylinder")
    turnpoint =     haf.download_task_cylinders(db_race,"turnpoint")
    m = haf.add_task_to_map(m, startcylinder, turnpoint)
    m.fit_bounds(haf.get_task_bounds(startcylinder, turnpoint))

    #TODO add to frontend the site info: name, elevation, distance, avg grade, elev min max

    #%% frontend gpx uploader
    with st.form(key='upload_gpx'):
        gpx_file = st.file_uploader(label = 'Upload your gpx tracklog for evaluation:', type = 'gpx')
        athlete_name = st.text_input("Athlete's name")
        st.form_submit_button('Submit')

    #%% actions if user uploads gpx file
    while gpx_file is not None: #"while" instead of "if" to apply "break" during validation down below

        #%% read gpx file and add to map
        gpx = gpxpy.parse(gpx_file)
        pdf = haf.gpx_to_df(gpx)
        pdf_to_antpath = pdf[["latitude","longitude"]].values.tolist()
        AntPath(pdf_to_antpath, color='blue', weight=4.5, opacity=.5, fitBounds = True).add_to(m)
        m.fit_bounds(haf.get_gpx_bounds(pdf)) 

        #%% validate user gpx

        pdf = haf.identify_up_and_down_segments(pdf, startcylinder, turnpoint)

        #check if the competition task was executed properly 
        if pdf.inside_start.sum() < 1:
            st.error("Tracklog does not cross the start cylinder!")
            break
        if pdf.inside_tp.sum() < 1:
            st.error("Tracklog does not cross the turnpoint!")
            break
        if pdf.segment_down.sum() == 0:
            st.error("Trackloig does not go back to the start cylinder!")
            break
        if pdf.segment_up.sum() == 0:
            st.error("Running up does not start within the start cylinder!")
            break
        if pdf.query("segment_up").idx.max() > pdf.query("segment_down").idx.min():
            st.error('Order of tagging the cylinders is incorrect')
            break

        #%% Extract results info from gpx

        # calculate up and down timedeltas
        time_up   = pdf[pdf['segment_up'  ] == True].time.max() - pdf[pdf['segment_up'  ] == True].time.min()
        time_down = pdf[pdf['segment_down'] == True].time.max() - pdf[pdf['segment_down'] == True].time.min()

        result_new = {
            "athlete" : athlete_name,
            "date" : pdf.time[1].strftime('%Y.%m.%d'),
            "time_up" :   haf.strfdelta(time_up,   '%H:%M:%S'),
            "time_down" : haf.strfdelta(time_down, '%H:%M:%S'),
            "start_time": pdf.query("segment_up").time.min() #for validation
            }

        #upload new result to firestore
        resp = haf.upload_new_task_result(db_race,result_new)

        #update results df
        df_results = haf.download_task_results(db_race)

        gpx_file = None #exiting the while loop

    #%% display outputs (end of 'while gpx_file is not None')
    df_results.columns = ['Ranking','Athlete', 'Date', 'Time up', 'Time down', "Start time", "Time of submit"]
    st.dataframe(df_results.iloc[:,0:5], use_container_width = True) 
    m.to_streamlit()
#%% run app
app()