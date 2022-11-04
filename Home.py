#%% Import libs & config
import streamlit as st

#%% Frontend sidebar
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

#%% Main app
def app():
    #%% Frontend headers
    st.subheader('Welcome to the site of')   
    st.title('Hike and Fly Records')    
    st.subheader('⛰️ 🥾 🪂 🏆')
    st.text('Pick an option from the left menu!')

#%% Run app
app()