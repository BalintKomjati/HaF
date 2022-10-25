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

def connect_firestore():
    """connect to the app's firestore database"""
    if os.environ.get("COMPUTERNAME", "REMOTE") == 'DESKTOP-1UKNJQ5':
        db = firestore.Client.from_service_account_json(".streamlit/firebase-hafr-key.json")
    else:
        key_dict = json.loads(st.secrets["textkey"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        db = firestore.Client(credentials=creds, project="hafr-e2128")
    return(db)

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

def get_task_cylinders(db_race,cylinder_name):
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
    gdf = gpd.GeoDataFrame( pdf, 
                            geometry=gpd.points_from_xy(pdf.longitude, pdf.latitude),
                            crs="EPSG:4326"
                            )
    bounds = gdf.to_crs(epsg="4326").bounds
    west = min(bounds["minx"])
    south = min(bounds["miny"])
    east = max(bounds["maxx"])
    north = max(bounds["maxy"])

    bbox = [[south, east], [north, west]]

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

#########################


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

