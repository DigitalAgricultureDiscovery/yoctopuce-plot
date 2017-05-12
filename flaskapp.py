# -*- coding: utf-8 -*-

from flask import Flask, render_template, flash, request, url_for, redirect, session, jsonify, make_response, send_file
from wtforms import Form, BooleanField, TextField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
from MySQLdb import escape_string as thwart
from dbconnect import connection
import gc
import os
import ast
import json
import os
import datetime, time
import pytz
from math import pi

from dateutil import tz
from tinydb import TinyDB, Query
from collections import defaultdict
import numpy as np
from content_management import Content

from bokeh.plotting import figure, curdoc, show
from bokeh.resources import CDN, INLINE
from bokeh.embed import file_html, components
from bokeh.client import push_session
from bokeh.util.browser import view
from bokeh.util.string import encode_utf8
from bokeh.models import *
from bokeh.layouts import row, gridplot


TOPIC_DICT = Content()

app = Flask(__name__)
app.secret_key = 'super secret key'


# Load database
db = TinyDB('/var/www/html/flaskapp/db.json')
Query = Query()

# Initial Setup
# Define colors
colors = {
'Black': '#000000',
'Red':   '#FF0000',
'Green': '#00FF00',
'Blue':  '#0000FF',
}



# Get submit value for plots
def getitem(obj, item, default):
    if item not in obj:
        return default
    else:
        return obj[item]

# Get the longest element in list
def GetMaxElement(all_data):
    longest_element = max(all_data, key=lambda k: len(k))
    return longest_element

# Load data to pandas dataframe
def data_pd_df():
    # Get the keys of the data, and sort them
    all_data = db.all()
    keys = GetMaxElement(all_data)

    # Merge dicts with the same keys
    dd = defaultdict(list)

    for d in db.all():
        for key, value in d.iteritems():
            dd[key].append(value)

    # Construct the pandas dataframe
    df = pd.DataFrame.from_dict(dd, orient='index')
    df = df.transpose()
    # Convert timestamp to readable version
    df['timestamp_int'] = pd.to_numeric(df['timestamp'])
    df['Recorded Time'] = pd.to_datetime(df['timestamp'], unit='s')
    
    # convert_time = lambda x: utc_to_local(x)
    # df['Recorded Time'].map(convert_time)

    df = df.sort(['timestamp_int'])
    return df, keys

# Determine y title and label
def determine_y_label(parameter):
    parameter_s = parameter.split('.', 1)[1]
    if parameter_s == 'humidity':
        f_title = 'Humidity vs Time'
        f_ylabel = 'Humidity (%)'
    elif parameter_s == 'temperature':
        f_title = 'Temperature vs Time'
        f_ylabel = 'Temperature (°C)'
    elif parameter_s == 'pressure':
        f_title = 'Pressure vs Time'
        f_ylabel = 'Pressure (kPa)'
    elif parameter_s == 'lightSensor':
        f_title = 'Lightness vs Time'
        f_ylabel = 'Lightness (lux)'
    elif parameter_s == 'latitude':
        f_title = 'Latitude vs Time'
        f_ylabel = 'Latitude (°)'
    elif parameter_s == 'groundSpeed':
        f_title = 'Ground Speed vs Time'
        f_ylabel = 'Ground Speed (km/hr)'
    elif parameter_s == 'altitude':
        f_title = 'Altitude vs Time'
        f_ylabel = 'Altitude (°)'
    elif parameter_s == 'longitude':
        f_title = 'Longitude vs Time'
        f_ylabel = 'Longitude (°)'
    return f_title, f_ylabel

# Drop undesired columns
def drop_columns(df):
    column_headers = list(df)
    drop_list = ['dataLogger', 'hubPort', 'realTimeClock', 'network', 'timestamp', 'wireless', 'gps']
    for index in column_headers:
        for item in drop_list:
            if item in index:
                df = df.drop(index, 1)
    return df
 
# Drop undesired keys 
def drop_keys(keys):
    drop_list = ['dataLogger', 'hubPort', 'realTimeClock', 'network', 'timestamp', 'wireless', 'gps']
    delete_keys = []
    for index in keys:
        for item in drop_list:
            if item in index:
                delete_keys.append(index)
    new_keys = [a for a in keys if a not in delete_keys]
    return new_keys

# Get desired columns
def get_columns(df, device_names):
    column_headers = list(df)
    df_new = pd.DataFrame()
    for index in column_headers:
        for item in device_names:
            if item in index:
                df_new[index] = df[index]
    df_new['Recorded Time'] = df['Recorded Time']
    return df_new

# Get desired keys 
def get_keys(keys, device_names):
    new_keys = []
    for index in keys:
        for item in device_names:
            if item in index:
                new_keys.append(index)
    return new_keys

# Login required decorator
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash("You need to login first")
            return redirect(url_for('login_page'))
    return wrap

# Retrieve registered devices
def retrieve_registered_devices():
    username = session['username']
    c, conn = connection()
    x = c.execute("SELECT * FROM user_devices WHERE username = (%s)",
                    [(thwart(username))])
    device_names = []
    device_name = c.fetchone()
    while device_name is not None:
        device_names.append(device_name[2])
        device_name = c.fetchone()        
    conn.commit()
    c.close()
    conn.close()
    gc.collect()
    return device_names

# Register device decorator
def register_device_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        device_names = retrieve_registered_devices()
        if len(device_names) != 0:
            return f(*args, **kwargs)
        else:
            flash("You need to register a device first")
            return redirect(url_for('register_device'))
    return wrap


# Homepage
TOPIC_DICT = Content()
@app.route('/index/')
@app.route('/')
def homepage():
    flash('Welcome!')
    return render_template("homepage.html", TOPIC_DICT=TOPIC_DICT)


@app.route('/register_device/', methods=['GET','POST'])
@login_required
def register_device():
    if request.method == 'GET':
        return render_template('register_device.html')
    elif request.method == 'POST':
        device_serial_number = request.form['Device Serial Number']
       
        username = session['username']
        c, conn = connection()
        x = c.execute("SELECT * FROM user_devices WHERE username = (%s) AND device_name = (%s)",
                          ([(thwart(username))], [(thwart(device_serial_number))]))

        if int(x) > 0:
            flash("That device is already registered.")
            return redirect(url_for("register_device"))
        
        elif device_serial_number == '':
            return redirect(url_for("register_device"))

        else:
            c.execute("INSERT INTO user_devices (username, device_name) VALUES (%s, %s)",
                            (thwart(username), thwart(device_serial_number)))
            conn.commit()
            c.close()
            conn.close()
            gc.collect()

            flash("Success!")
            return redirect(url_for("register_device"))

    else:
        return "<h2>Invalid request</h2>"


@app.route('/rawdata/', methods=['Get'])
@login_required
@register_device_required
def rawdata():
    df, keys = data_pd_df()
    df = drop_columns(df)
    device_names = retrieve_registered_devices()
    df = get_columns(df, device_names)
    # Set timestamp as index
    df.set_index('Recorded Time', inplace=True)    
    
    # Output dataframe to html
    df_html = df.to_html()
    return render_template("rawdata.html", df_html=df_html)

@app.route('/return-files/')
def return_files():
    df, keys = data_pd_df()
    df = drop_columns(df)
    device_names = retrieve_registered_devices()
    df = get_columns(df, device_names)
    # Set timestamp as index
    df.set_index('Recorded Time', inplace=True)    
    
    # Output dataframe to csv
    df_csv = df.to_csv()

    response = make_response(df_csv)
    cd = 'attachment; filename=data.csv'
    response.headers['Content-Disposition'] = cd 
    response.mimetype='text/csv'

    return response 


@app.route('/plot/', methods=['GET'])
@login_required
@register_device_required
def plot():
    # Load data to pandas dataframe
    df, keys = data_pd_df()
    keys = drop_keys(keys)
    device_names = retrieve_registered_devices()
    keys = get_keys(keys, device_names)

    timestamps = df['Recorded Time']
    # Grab the inputs arguments from the URL
    args = request.args

    # Embed the plot
    # Get all the form arguments in the url with defaults    
    color = getitem(args, 'color', 'Black')
    _from = getitem(args, '_from', min(timestamps))
    to = getitem(args, 'to', max(timestamps)) 
    parameter = getitem(args, 'parameter', keys[0]) 
    
    # Convert to datetime format
    if type(_from).__name__ != 'Timestamp':
        # Convert string to datetime
        _from = datetime.datetime.strptime(_from, '%Y-%m-%d %H:%M:%S')
        to = datetime.datetime.strptime(to, '%Y-%m-%d %H:%M:%S')
    
    f_title, f_ylabel = determine_y_label(parameter)

    # Set the range of x 
    int_timestamps = df['timestamp_int']
    # This part need to be consider later: Timezone
    int_from = int(time.mktime(_from.timetuple()))
    int_to = int(time.mktime(to.timetuple()))

    x = int_timestamps[(int_from < int_timestamps) & (int_timestamps < int_to)]
    x = pd.to_datetime(x, unit='s')
    # Convert string to float
    y = df[parameter].convert_objects(convert_numeric=True)

    # Create the graph
    hover = HoverTool(
        tooltips=[
            ("(x,y)", "($x, $y)")
        ]
    )
    TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), hover, SaveTool(), CrosshairTool(), PanTool()]
    p=figure(title=f_title, x_axis_label='Time', y_axis_label=f_ylabel, 
         width=800, height=400, x_axis_type="datetime",  tools=TOOLS)
    
    p.xaxis.formatter=DatetimeTickFormatter(
        microseconds=["%m/%d/%y %I:%M:%S %p"],
        milliseconds=["%m/%d/%y %I:%M:%S %p"],
        seconds=["%m/%d/%y %I:%M:%S %p"],
        minsec=["%m/%d/%y %I:%M:%S %p"],
        minutes=["%m/%d/%y %I:%M:%S %p"],
        hourmin=["%m/%d/%y %I:%M:%S %p"],
        hours=["%m/%d/%y %I:%M:%S %p"],
        days=["%m/%d/%y %I:%M:%S %p"],
        months=["%m/%d/%y %I:%M:%S %p"],
        years=["%m/%d/%y %I:%M:%S %p"],
    )
    p.xaxis.major_label_orientation = pi/4

    r = p.line(x, y, color=colors[color], alpha=0.5, line_width=3)
    s = p.circle(x, y, color=colors[color], alpha=0.5,)

    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()

    script, div = components(p)

    html = render_template(
        'plot.html',
        plot_script=script,
        plot_div=div,
        js_resources=js_resources,
        css_resources=css_resources,
        color=color,
        _from=_from,
        to=to,
        parameter=parameter,
        keys=keys
    )
    return encode_utf8(html)


@app.route('/multiple_plot/', methods=["GET","POST"])
@login_required
@register_device_required
def multiple_plot():
    # Load data to pandas dataframe
    df, keys = data_pd_df()
    keys = drop_keys(keys)
    device_names = retrieve_registered_devices()
    keys = get_keys(keys, device_names)

    timestamps = df['Recorded Time']
    # Grab the inputs arguments from the URL
    args = request.args
    
    # Embed the plot
    # Get all the form arguments in the url with defaults
    _from = getitem(args, '_from', min(timestamps))
    to = getitem(args, 'to', max(timestamps)) 

    # Convert to datetime format
    if type(_from).__name__ != 'Timestamp':
        # Convert string to datetime
        _from = datetime.datetime.strptime(_from, '%Y-%m-%d %H:%M:%S')
        to = datetime.datetime.strptime(to, '%Y-%m-%d %H:%M:%S')

    # Set the range of x 
    int_timestamps = df['timestamp_int']
    # This part need to be consider later: Timezone
    int_from = int(time.mktime(_from.timetuple()))
    int_to = int(time.mktime(to.timetuple()))

    x = int_timestamps[(int_from < int_timestamps) & (int_timestamps < int_to)]
    x = pd.to_datetime(x, unit='s')

    parameters = request.form.getlist('sensor_type')

    if len(parameters)==0:
        parameter = 'METEOMK1-73F19.humidity'
        # Convert string to float
        y = df[parameter].convert_objects(convert_numeric=True)

        f_title, f_ylabel = determine_y_label(parameter)

        # Create the graph
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig=figure(title=f_title, x_axis_label='Time', y_axis_label=f_ylabel, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r = fig.line(x, y, alpha=0.5, line_width=3)
        s = fig.circle(x, y, alpha=0.5)
    
    elif len(parameters)==1:        
        y = df[parameters[0]].convert_objects(convert_numeric=True)

        f_title, f_ylabel = determine_y_label(parameters[0])

        # Create the graph
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig=figure(title=f_title, x_axis_label='Time', y_axis_label=f_ylabel, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r = fig.line(x, y, alpha=0.5, line_width=3)
        s = fig.circle(x, y, alpha=0.5)
    
    elif len(parameters)==2:
        y1 = df[parameters[0]].convert_objects(convert_numeric=True)

        f_title1, f_ylabel1 = determine_y_label(parameters[0])

        # Create the first graph
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig1 = figure(title=f_title1, x_axis_label='Time', y_axis_label=f_ylabel1, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r1 = fig1.line(x, y1, alpha=0.5, line_width=3)
        s1 = fig1.circle(x, y1, alpha=0.5)
        
        y2 = df[parameters[1]].convert_objects(convert_numeric=True)

        f_title2, f_ylabel2 = determine_y_label(parameters[1])

        # Create the second graph
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig2 = figure(title=f_title2, x_axis_label='Time', y_axis_label=f_ylabel2, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r2 = fig2.line(x, y2, alpha=0.5, line_width=3)
        s2 = fig2.circle(x, y2, alpha=0.5)

        fig = row(fig1, fig2)

    elif len(parameters)==3:
        # Create the first graph
        y1 = df[parameters[0]].convert_objects(convert_numeric=True)

        f_title1, f_ylabel1 = determine_y_label(parameters[0])

        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig1 = figure(title=f_title1, x_axis_label='Time', y_axis_label=f_ylabel1, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r1 = fig1.line(x, y1, alpha=0.5, line_width=3)
        s1 = fig1.circle(x, y1, alpha=0.5,)
        
        # Create the second graph
        y2 = df[parameters[1]].convert_objects(convert_numeric=True)

        f_title2, f_ylabel2 = determine_y_label(parameters[1])
        
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig2 = figure(title=f_title2, x_axis_label='Time', y_axis_label=f_ylabel2, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r2 = fig2.line(x, y2, alpha=0.5, line_width=3)
        s2 = fig2.circle(x, y2, alpha=0.5)

        # Create the third graph
        y3 = df[parameters[2]].convert_objects(convert_numeric=True)

        f_title3, f_ylabel3 = determine_y_label(parameters[2])
        
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig3 = figure(title=f_title3, x_axis_label='Time', y_axis_label=f_ylabel3, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r3 = fig3.line(x, y3, alpha=0.5, line_width=3)
        s3 = fig3.circle(x, y3, alpha=0.5)

        fig = row(fig1, fig2, fig3)
    
    elif len(parameters)==4:
        # Create the first graph
        y1 = df[parameters[0]].convert_objects(convert_numeric=True)

        f_title1, f_ylabel1 = determine_y_label(parameters[0])

        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig1 = figure(title=f_title1, x_axis_label='Time', y_axis_label=f_ylabel1, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r1 = fig1.line(x, y1, alpha=0.5, line_width=3)
        s1 = fig1.circle(x, y1, alpha=0.5,)
        
        # Create the second graph
        y2 = df[parameters[1]].convert_objects(convert_numeric=True)

        f_title2, f_ylabel2 = determine_y_label(parameters[1])
        
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig2 = figure(title=f_title2, x_axis_label='Time', y_axis_label=f_ylabel2, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r2 = fig2.line(x, y2, alpha=0.5, line_width=3)
        s2 = fig2.circle(x, y2, alpha=0.5)
        
        # Create the third graph
        y3 = df[parameters[2]].convert_objects(convert_numeric=True)

        f_title3, f_ylabel3 = determine_y_label(parameters[2])
        
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig3 = figure(title=f_title3, x_axis_label='Time', y_axis_label=f_ylabel3, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r3 = fig3.line(x, y3, alpha=0.5, line_width=3)
        s3 = fig3.circle(x, y3, alpha=0.5)

        # Create the third graph
        y4 = df[parameters[3]].convert_objects(convert_numeric=True)

        f_title4, f_ylabel4 = determine_y_label(parameters[3])
        
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig4 = figure(title=f_title4, x_axis_label='Time', y_axis_label=f_ylabel4, 
            width=300, height=300, x_axis_type="datetime",  tools=TOOLS)

        r4 = fig4.line(x, y4, alpha=0.5, line_width=3)
        s4 = fig4.circle(x, y4, alpha=0.5)

        fig = gridplot([[fig1, fig2], [fig3, fig4]])

    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()

    script, div = components(fig)

    html = render_template(
        'multiple_plot.html',
        plot_script=script,
        plot_div=div,
        js_resources=js_resources,
        css_resources=css_resources,
        _from=_from,
        to=to,
        keys=keys
    )
    return encode_utf8(html)


@app.route('/multiple_line/', methods=['GET', "POST"])
@login_required
@register_device_required
def multiple_line():
    # Load data to pandas dataframe
    df, keys = data_pd_df()
    keys = drop_keys(keys)
    device_names = retrieve_registered_devices()
    keys = get_keys(keys, device_names)

    timestamps = df['Recorded Time']
    # Grab the inputs arguments from the URL
    args = request.args

    # Embed the plot
    # Get all the form arguments in the url with defaults
    _from = getitem(args, '_from', min(timestamps))
    to = getitem(args, 'to', max(timestamps)) 

    # Convert to datetime format
    if type(_from).__name__ != 'Timestamp':
        # Convert string to datetime
        _from = datetime.datetime.strptime(_from, '%Y-%m-%d %H:%M:%S')
        to = datetime.datetime.strptime(to, '%Y-%m-%d %H:%M:%S')

    # Set the range of x 
    int_timestamps = df['timestamp_int']
    # This part need to be consider later: Timezone
    int_from = int(time.mktime(_from.timetuple()))
    int_to = int(time.mktime(to.timetuple()))

    x = int_timestamps[(int_from < int_timestamps) & (int_timestamps < int_to)]
    x = pd.to_datetime(x, unit='s')

    parameters = request.form.getlist('sensor_type')

    if len(parameters)==0:
        parameter = 'METEOMK1-73F19.humidity'
        # Convert string to float
        y = df[parameter].convert_objects(convert_numeric=True)

        f_title, f_ylabel = determine_y_label(parameter)

        # Create the graph
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig=figure(title=f_title, x_axis_label='Time', y_axis_label=f_ylabel, 
            width=800, height=400, x_axis_type="datetime",  tools=TOOLS)

        r = fig.line(x, y, alpha=0.5, line_width=3)
        s = fig.circle(x, y, alpha=0.5)

    elif len(parameters)==1:        
        y = df[parameters[0]].convert_objects(convert_numeric=True)

        f_title, f_ylabel = determine_y_label(parameters[0])

        # Create the graph
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig=figure(title=f_title, x_axis_label='Time', y_axis_label=f_ylabel, 
            width=800, height=400, x_axis_type="datetime",  tools=TOOLS)

        r = fig.line(x, y, alpha=0.5, line_width=3)
        s = fig.circle(x, y, alpha=0.5)
    
    elif len(parameters)==2:
        y1 = df[parameters[0]].convert_objects(convert_numeric=True)
        y2 = df[parameters[1]].convert_objects(convert_numeric=True)

        f_title1, f_ylabel1 = determine_y_label(parameters[0])

        # Create the first graph
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        fig = figure(title=f_title1, x_axis_label='Time', y_axis_label=f_ylabel1, 
            width=800, height=400, x_axis_type="datetime",  tools=TOOLS)

        r1 = fig.line(x, y1, alpha=0.5, line_width=3, color='Black', legend=parameters[0])
        s1 = fig.circle(x, y1, alpha=0.5, color='Black')
        r2 = fig.line(x, y2, alpha=0.5, line_width=3, color='Blue', legend=parameters[1])
        s2 = fig.circle(x, y2, alpha=0.5, color='Blue')
        
    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()

    script, div = components(fig)

    html = render_template(
        'multiple_line.html',
        plot_script=script,
        plot_div=div,
        js_resources=js_resources,
        css_resources=css_resources,
        _from=_from,
        to=to,
        keys=keys
    )
    return encode_utf8(html)


@app.route('/realtime_plot/', methods=['Get', 'POST'])
@login_required
@register_device_required
def realtime_plot(): 
    # Load data to pandas dataframe
    df, keys = data_pd_df()
    keys = drop_keys(keys)
    device_names = retrieve_registered_devices()
    keys = get_keys(keys, device_names)

    if request.method == 'GET':   
        # Grab the inputs arguments from the URL
        args = request.args

        # Get all the form arguments in the url with defaults
        color = getitem(args, 'color', 'Black') 
        parameter = getitem(args, 'parameter', keys[0])

        html = render_template(
            'create_realtime_plot.html',
            color=color,
            parameter=parameter,
            keys=keys
        )
        return encode_utf8(html)

    elif request.method == 'POST':
        #read form data and save it
        parameter = request.form['parameter']
        color = request.form['color']

        f_title, f_ylabel = determine_y_label(parameter)

        timestamps = df['timestamp_int']
        start_time = time.time()
        x = timestamps[(start_time < timestamps)]
        x = pd.to_datetime(x, unit='s') 
        y = df[parameter]
        start_time0 = datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
        
        TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
        p=figure(title=f_title, x_axis_label='Time', y_axis_label=f_ylabel, 
            width=800, height=400, x_axis_type="datetime",  tools=TOOLS)

        p.xaxis.formatter=DatetimeTickFormatter(
            microseconds=["%m/%d/%y %I:%M:%S %p"],
            milliseconds=["%m/%d/%y %I:%M:%S %p"],
            seconds=["%m/%d/%y %I:%M:%S %p"],
            minsec=["%m/%d/%y %I:%M:%S %p"],
            minutes=["%m/%d/%y %I:%M:%S %p"],
            hourmin=["%m/%d/%y %I:%M:%S %p"],
            hours=["%m/%d/%y %I:%M:%S %p"],
            days=["%m/%d/%y %I:%M:%S %p"],
            months=["%m/%d/%y %I:%M:%S %p"],
            years=["%m/%d/%y %I:%M:%S %p"],
        )
        p.xaxis.major_label_orientation = pi/4

        r = p.line(x, y, color=colors[color], alpha=0.5, line_width=3)
        s = p.circle(x, y, color=colors[color], alpha=0.5,)

        js_resources = INLINE.render_js()
        css_resources = INLINE.render_css()

        script, div = components(p)

        # Use cookies to store parameter and color
        resp = make_response(render_template('realtime_plot.html',
            plot_script=script,
            plot_div=div,
            js_resources=js_resources,
            css_resources=css_resources,
            start_time=start_time0,
            color=color,
            parameter=parameter,
            keys=keys,
        ))
        resp.set_cookie('parameter', parameter)
        resp.set_cookie('color', color)
        resp.set_cookie('Start Time', bytes(start_time))

        return resp

    else:
        return "<h2>Invalid request</h2>"

@app.route('/realtime_plot_update/', methods = ['POST'])
def update_plot():
    # Load data to pandas dataframe
    df, keys = data_pd_df()

    timestamps = df['timestamp_int']
    # Get cookies
    parameter = request.cookies.get('parameter')
    color = request.cookies.get('color')
   
    f_title, f_ylabel = determine_y_label(parameter)

    start_time = float(request.cookies.get('Start Time'))
    x = timestamps[(start_time < timestamps)]
    x = pd.to_datetime(x, unit='s')
    y = df[parameter]
    start_time = datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')  
    
    TOOLS = [BoxSelectTool(), WheelZoomTool(), ResizeTool(), BoxZoomTool(), ResetTool(), SaveTool(), PanTool()]
    p=figure(title=f_title, x_axis_label='Time', y_axis_label=f_ylabel, 
         width=800, height=400, x_axis_type="datetime",  tools=TOOLS)

    p.xaxis.formatter=DatetimeTickFormatter(
        microseconds=["%m/%d/%y %I:%M:%S %p"],
        milliseconds=["%m/%d/%y %I:%M:%S %p"],
        seconds=["%m/%d/%y %I:%M:%S %p"],
        minsec=["%m/%d/%y %I:%M:%S %p"],
        minutes=["%m/%d/%y %I:%M:%S %p"],
        hourmin=["%m/%d/%y %I:%M:%S %p"],
        hours=["%m/%d/%y %I:%M:%S %p"],
        days=["%m/%d/%y %I:%M:%S %p"],
        months=["%m/%d/%y %I:%M:%S %p"],
        years=["%m/%d/%y %I:%M:%S %p"],
    )
    p.xaxis.major_label_orientation = pi/4

    r = p.line(x, y, color=colors[color], alpha=0.5, line_width=3)
    s = p.circle(x, y, color=colors[color], alpha=0.5,)
    script, div = components(p)

    import json

    return json.dumps({"plot_script": script, "plot_div": div})


@app.route('/MappingGeoData/', methods=['POST', 'GET'])
@login_required
@register_device_required
def MappingGeoData():
    df, keys = data_pd_df()
    keys = drop_keys(keys)
    device_names = retrieve_registered_devices()
    keys = get_keys(keys, device_names)
    gps_serial_number = []
    # Get GPS sensor serial number
    for item in device_names:
        if 'YGNSSMK1' in item:
            gps_serial_number.append(item) 

    if len(gps_serial_number) == 0:
        flash('Need to register a GPS Sensor first!')
        return redirect(url_for('register_device'))

    def generate_marker_content(i):
        content = '<b>' + str(df["Recorded Time"][i]) + '</b>' + '<br>'
        for item in keys:
            content = content + item + ':' + str(df[item][i]) + '<br>'
        return content.encode('ascii','ignore')

    latitude_name = gps_serial_number[0] + '.latitude'
    longitude_name = gps_serial_number[0] + '.longitude'

    lat = np.array(pd.to_numeric(df[latitude_name]))
    lon = np.array(pd.to_numeric(df[longitude_name]))
    converter = 1000
    lat= lat / converter
    lon= lon / converter
    # Get rid of nan
    lat = lat[~np.isnan(lat)]
    lon = lon[~np.isnan(lon)]
    lat = map(np.asscalar, lat)
    lon = map(np.asscalar, lon)

    i = 0
    planes = []
    while i < len(lat):
        marker = []
        # marker.append(str(df["Recorded Time"][i]))
        content = generate_marker_content(i)
        marker.append(content)
        marker.append(lat[i])
        marker.append(lon[i])
        planes.append(marker)
        # planes[i] = marker
        i += 1

    # planes = json.dumps(planes)

    # flash(planes)
    html = render_template(
        'MappingGeoDataJS.html',
        planes=planes
    )
    return encode_utf8(html)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html")


@app.route('/user_info/')
@login_required
def user_info():
    device_names = retrieve_registered_devices()
    return render_template('user_info.html', device_names=device_names)


@app.route("/logout/")
@login_required
def logout():
    session.clear()
    flash("You have been logged out!")
    gc.collect()
    return redirect(url_for('homepage'))


@app.route('/login/', methods = ['GET', 'POST'])
def login_page():
    error = ''
    try:
        c, conn = connection()
        if request.method == "POST":

            data = c.execute("SELECT * FROM users WHERE username = (%s)",
                            [thwart(request.form['username'])])
            data = c.fetchone()[2]

            if sha256_crypt.verify(request.form['password'], data):
                session['logged_in'] = True
                session['username'] = request.form['username']

                flash("You are now logged in!")
                return redirect(url_for("homepage"))
            else:
                error = "Invalid credentials, try again."
        
        gc.collect()
        return render_template("login.html", error=error)

    except Exception as e:
        # flash(e)
        error = "Invalid credentials, try again."
        return render_template("login.html", error=error)


class RegistrationForm(Form):
    username = TextField('Username', [validators.Length(min=4, max=20)])
    email = TextField('Email Address', [validators.Length(min=6, max=50)])
    password = PasswordField('New Password', [
        validators.Required(),
        validators.EqualTo('confirm', message='Passwords must match')
    ])
    confirm = PasswordField('Repeat Password')
    accept_tos = BooleanField('I accept the <a href = "/tos/">Terms of Service</a> and <a href = "/privacy/">Privacy Notice</a> (updated April 12, 2017)', [validators.Required()])    



@app.route('/register/', methods=["GET","POST"])
def register_page():
    try:
        form = RegistrationForm(request.form)

        if request.method == "POST" and form.validate():
            username  = form.username.data
            email = form.email.data
            password = sha256_crypt.encrypt((str(form.password.data)))
            c, conn = connection()

            x = c.execute("SELECT * FROM users WHERE username = (%s)",
                          [(thwart(username))])

            if int(x) > 0:
                flash("That username is already taken, please choose another")
                return render_template('register.html', form=form)

            else:
                c.execute("INSERT INTO users (username, password, email, tracking) VALUES (%s, %s, %s, %s)",
                          (thwart(username), thwart(password), thwart(email), thwart("Purdue")))
                
                conn.commit()
                flash("Thanks for registering!")
                c.close()
                conn.close()
                gc.collect()

                session['logged_in'] = True
                session['username'] = username

                return redirect(url_for('homepage'))

        return render_template("register.html", form=form)

    except Exception as e:
        return(str(e))


@app.route('/sensordata/', methods=['POST'])
def get_sensordata():
    if request.method == 'POST':
        json_callback = request.get_json()
        db.insert(json_callback)

    else:
        return "<h2>Invalid request</h2>"
    
    return 'Success'


if __name__ == "__main__":
    print(__doc__)
    app.run(debug=True)
