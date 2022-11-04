#%% Import libs & config
import pandas as pd
import streamlit as st
import geopandas as gpd
import geopy.distance
import gpxpy
import json
import os
import firebase_admin
from firebase_admin import credentials, storage, firestore
from datetime import datetime
from numpy import mean, min, max
import leafmap.foliumap as leafmap
from folium import Marker, Circle
from folium.plugins import AntPath, MeasureControl
from folium.features import CustomIcon
from string import Template

import haf_module as haf

# Authenticate to Firebase
haf.initialize_connection_to_firebase() 
db_race = firestore.client().collection('races').document('eged')
bucket = storage.bucket()

#%% Main app
def app():
    #%% Frontend headers 
    st.set_page_config(layout="wide")
    st.title('Hike-and-Fly Site Records - Eged')    
    st.text('')

    #%% Create map and download task results
    df_results = haf.download_task_results(db_race)

    m = haf.create_basis_map()
    startcylinder = haf.download_task_cylinders(db_race,"startcylinder")
    turnpoint =     haf.download_task_cylinders(db_race,"turnpoint")
    m = haf.add_task_to_map(m, startcylinder, turnpoint)
    m.fit_bounds(haf.get_task_bounds(startcylinder, turnpoint))

    #TODO add to frontend the site info: name, elevation, distance, avg grade, elev min max

    #%% Frontend gpx uploader
    with st.form(key='upload_gpx'):
        gpx_file = st.file_uploader(label = 'Upload your gpx tracklog for evaluation:', type = 'gpx')
        athlete_name = st.text_input("Athlete's name")
        st.form_submit_button('Submit')

    #%% Actions if user uploads gpx file
    while gpx_file is not None: #"while" instead of "if" to apply "break" during validation down below

        #%% Read gpx file and add to map
        gpx = gpxpy.parse(gpx_file)  # type: ignore
        pdf = haf.gpx_to_df(gpx)
        pdf_to_antpath = pdf[["latitude","longitude"]].values.tolist()
        AntPath(pdf_to_antpath, color='blue', weight=4.5, opacity=.5, fitBounds = True).add_to(m)
        m.fit_bounds(haf.get_gpx_bounds(pdf)) 

        #%% Validate uploaded gpx

        #check if name was supplied with the gpx
        if not athlete_name:
            st.error("You cannot leave the athlete's name blank")
            break

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

        # calculate other result components
        ts = datetime.now()
        idx_max = pdf.query("segment_down").idx.max()
        finish_coords = str(pdf.query('idx == @idx_max').longitude.item()) + ',' + str(pdf.query('idx == @idx_max').latitude.item())

        result_new = {
            "athlete" : athlete_name,
            "date" : pdf.time[1].strftime('%Y.%m.%d'),
            "time_up" :   haf.strfdelta(time_up,   '%H:%M:%S'),
            "time_down" : haf.strfdelta(time_down, '%H:%M:%S'),
            "start_time" : pdf.query("segment_up").time.min(),      #for validation
            "finish_time" :  pdf.query("segment_down").time.max(),  #for validation
            "finish_coords" : finish_coords,                        #for validation
            "timestamp" : ts #gpx file reference
            }

        #%% validate new result
        if len(df_results[(df_results.athlete    == result_new['athlete']) & 
                          (df_results.start_time == result_new['start_time'])] ) > 0:
                          st.error('Result already submitted for the same athlete and time')
                          break

        if len(df_results[(df_results.time_up     == result_new['time_up']) & 
                          (df_results.finish_coords == result_new['finish_coords'])] ) > 0:
                          st.error('This tracklog have already been uploaded')
                          break

        #%% upload to firebase

        #upload new result to firestore
        r1 = haf.upload_new_task_result(db_race,result_new)
        #save gpx file of new result
        r2 = haf.upload_new_gpx(bucket, ts, gpx_file)

        #update results df
        df_results = haf.download_task_results(db_race)

        st.success("Successfull upload! Your result was added to the rankings.")

        gpx_file = None #exiting the while loop

    #%% Display outputs (end of 'while gpx_file is not None')
    df_results.columns = ['Ranking','Athlete', 'Date', 'Time up', 'Time down', 
                          "Start Time", "Finish Time", "Finish Coordinates", "Time of submit"]  # type: ignore
    st.dataframe(df_results.iloc[:,0:5], use_container_width = True) 
    m.to_streamlit()
#%% Run app
app()