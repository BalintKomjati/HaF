import pandas as pd
import streamlit as st
import geopandas as gpd
import geopy.distance
import gpxpy
import json
import os
import firebase_admin
from firebase_admin import credentials
from firebase_admin import storage
from datetime import datetime
from numpy import mean, min, max
import leafmap.foliumap as leafmap
from folium import Marker, Circle
from folium.plugins import AntPath, MeasureControl
from folium.features import CustomIcon
from string import Template

def initialize_connection_to_firebase():
    """connect to the app's firebase database"""
    if os.environ.get("COMPUTERNAME", "REMOTE") == 'DESKTOP-1UKNJQ5':
        cred = credentials.Certificate('.streamlit/firebase-hafr-key.json')

    else:
        key_dict = json.loads(st.secrets["textkey"])
        cred = credentials.Certificate(key_dict)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'hafr-e2128.appspot.com'
        })

    return(firebase_admin.get_app())

def create_basis_map():
    """Define a stanard map used for visualizing the task and track later"""
    m = leafmap.Map(   
        draw_control       = False,
        measure_control    = False,
        fullscreen_control = False,
        search_control     = False,
        attribution_control= True)
    MeasureControl(position="topleft").add_to(m)
    m.add_basemap('HYBRID')
    m.add_xyz_service("xyz.OpenTopoMap")
    return(m)

def download_task_cylinders(db_race,cylinder_name):
    """Get coordinates and radius parameters of the task cylinders from firestore"""

    cylinder = db_race.collection('task').document(cylinder_name).get().to_dict()

    cylinder = Circle(
        location = (cylinder["lat"], cylinder["lon"]),
        radius = cylinder["radius"],
        color =      "green" if cylinder_name == "startcylinder" else "red",
        fill_color = "green" if cylinder_name == "startcylinder" else "red",
        tooltip = 'Start / Finish Cylider' if cylinder_name == "startcylinder" else "Turnpoint",
        )

    return(cylinder)    

def add_task_to_map(m,startcylinder, turnpoint):
    """Plot the task cylinders to the map with circles and icons, plus refit map to task bbox"""

    startcylinder.add_to(m)
    turnpoint.add_to(m)

    #add emojis to the cylinders
    tp_icon    = CustomIcon(icon_image='icons/repeat.png', icon_size=[20, 20])
    start_icon = CustomIcon(icon_image='icons/checkered_flag.png', icon_size=[20, 20])
    tp_emoji    = Marker(location=turnpoint.location, icon=tp_icon)
    start_emoji = Marker(location=startcylinder.location, icon = start_icon)
    start_emoji.add_to(m)
    tp_emoji.add_to(m)

    return(m)

def upload_new_task_result(db_race,result_new):
    """Upload the new task result received from the user to firestore"""
    db_result_new = db_race.collection('results').document()
    r = db_result_new.set(result_new)
    return(r)

def upload_new_gpx(bucket, ts, gpx_file):
    """Upload the new gpx file received from the user to firebase storage"""
    gpx_file.seek(0)
    blob = bucket.blob(ts.isoformat())
    r = blob.upload_from_file(gpx_file)
    #TODO ts should be added only to the object metadata 
    # (=unique identifier for the upload / completion of the task -- e.g. to store pics as well)
    return(r)

def download_task_results(db_race):
    """Get the task's current results list from firestore"""

    db_results = list(db_race.collection('results').stream())
    dict_results = list(map(lambda x: x.to_dict(), db_results))
    df_results = pd.DataFrame(dict_results)
    cn = ['athlete', 'date', 'time_up', "time_down", "start_time", "finish_time", "finish_coords", "timestamp"]
    #create blank dataframe if no result have been submitted ever to avoid errors downstream
    if len(df_results) == 0: 
        df_results = pd.DataFrame(columns=cn)
    else:
        df_results = df_results[cn]

    #add ranking and make it as the 1st col
    df_results = df_results.sort_values("time_up")
    df_results = df_results.reset_index(drop=True)
    df_results['ranking'] = df_results.index + 1
    cols = df_results.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    df_results = df_results[cols].sort_values("ranking")

    return(df_results)

def get_task_bounds(startcylinder, turnpoint):
    """Calculate the bbox of the task to fit the map accordingly"""
    north = max([turnpoint.location[0],startcylinder.location[0]])
    south = min([turnpoint.location[0],startcylinder.location[0]])
    east =  max([turnpoint.location[1],startcylinder.location[1]])
    west =  min([turnpoint.location[1],startcylinder.location[1]])

    bbox = [[south, east], [north, west]]

    return(bbox)

def get_gpx_bounds(pdf):
    """Calculate the bbox of the gpx tracklog to fit the map accordingly"""
    gdf = gpd.GeoDataFrame(pdf, 
                           geometry=gpd.points_from_xy(pdf.longitude, pdf.latitude),
                           crs="EPSG:4326"
                           )   # type: ignore
    bounds = gdf.to_crs(epsg="4326").bounds # type: ignore
    west = min(bounds["minx"])
    south = min(bounds["miny"])
    east = max(bounds["maxx"])
    north = max(bounds["maxy"])

    bbox = [[south, east], [north, west]] #might be more elegant with gdf.total_bounds()
    
    return(bbox)

def gpx_to_df(gpx):
    """Convert gpx to a dataframe one point at a time"""
    points = []
    #TODO handle the case when there are more than 1 tracks in the gpx file
    for segment in gpx.tracks[0].segments:
        for p in segment.points:
            points.append({
                'time': p.time, 
                'latitude': p.latitude,
                'longitude': p.longitude,
                'elevation': p.elevation,
            })
    pdf = pd.DataFrame.from_records(points)

    #this var will be used for exporting to firestore (timestamp is not json convertible)
    pdf['time_str'] = pdf['time'].astype(str)
    
    return(pdf)

def identify_up_and_down_segments(pdf, startcylinder, turnpoint):
    """Create new columns segment_up and segment_down 
    indicating if row is part of up or down leg of the task"""

    # identify sections when track is inside start / tp cylinders
    pdf['inside_start'] = pdf.apply(is_inside_cylinder, 
                                    cylinder_cord = startcylinder.location, 
                                    cylinder_radius = startcylinder.options['radius'], 
                                    axis = 1)
    pdf['inside_tp'] =    pdf.apply(is_inside_cylinder, 
                                    cylinder_cord = turnpoint.location, 
                                    cylinder_radius = turnpoint.options['radius'], 
                                    axis = 1)

    pdf['idx'] = pdf.index

    up_end     = pdf[pdf.inside_tp == True].idx.min()
    up_start   = pdf.loc[(pdf.inside_start == True) & (pdf.idx < up_end)].idx.max()
    down_start = pdf[pdf.inside_tp == True].idx.max()
    down_end   = pdf.loc[(pdf.inside_start == True) & (pdf.idx > down_start)].idx.min()

    pdf['segment_up']   = (pdf.idx > up_start  ) & (pdf.idx < up_end)
    pdf['segment_down'] = (pdf.idx > down_start) & (pdf.idx < down_end)

    return(pdf)

def is_inside_cylinder(df, cylinder_cord, cylinder_radius):
    """Identify if GPS record is inside cylinder"""
    station_coords = (df['latitude'], df['longitude'])
    d = geopy.distance.geodesic(cylinder_cord, station_coords).m < cylinder_radius
    return(d)

# definitions to transform timedelta to HH:MM:SS format
class DeltaTemplate(Template):
    delimiter = "%"

def strfdelta(tdelta, fmt):
    d = {"D": tdelta.days}
    hours, rem = divmod(tdelta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    d["H"] = '{:02d}'.format(hours)
    d["M"] = '{:02d}'.format(minutes)
    d["S"] = '{:02d}'.format(seconds)
    t = DeltaTemplate(fmt)
    return t.substitute(**d)

