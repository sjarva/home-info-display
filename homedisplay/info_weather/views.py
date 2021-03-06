# -*- coding: utf-8 -*-

from .models import Weather
from astral import Astral
from django.conf import settings
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View
import datetime
import json

WEEKDAYS_FI = ["ma", "ti", "ke", "to", "pe", "la", "su"]

def get_sun_info():
    sun_info = Astral()
    sun_info.solar_depression = 'civil'
    b = sun_info[settings.SUN_CITY].sun()
    return b

def json_default(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, datetime.time):
        return obj.isoformat()

def calculate_apparent_temperature(temperature, wind, humidity):
    wind /= 3.6
    windchill = (13.12 + 0.6215 * temperature - 11.37 * (wind ** 0.16) + 0.3965 * temperature * (wind ** 0.16))
    return round(windchill)

def get_wind_readable(wind):
    wind /= 3.6
    if wind < 0.2:
        return "tyyni"
    elif wind < 3.3:
        return "heikko"
    elif wind < 7.9:
        return "kohtalainen"
    elif wind < 13.8:
        return "navakka"
    elif wind < 20.7:
        return "kova"
    else:
        return "myrsky"

def get_weather_data():
    time_now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
    weather_objects = Weather.objects.filter(date__gte=time_now.date())
    forecast = {"hours": [], "current": None, "sun": None, "next": []}
    for item in weather_objects:
        i = model_to_dict(item)
        i["apparent_temperature"] = calculate_apparent_temperature(item.temperature, float(item.wind_speed), item.humidity)
        i["wind_speed_readable"] = get_wind_readable(float(item.wind_speed))
        i["weekday"] = i["date"].weekday()
        i["weekday_fi"] = WEEKDAYS_FI[i["weekday"]]
        if i["date"] == time_now.date() and i["hour"] == time_now.hour:
            forecast["current"] = i
        forecast["hours"].append(i)

    forecast["sun"] = get_sun_info()
    for k in forecast["sun"]:
        forecast["sun"][k] = unicode(forecast["sun"][k])


    hour = time_now.hour
    desired_entries = [("+2h", time_now + datetime.timedelta(hours=2))]
    if hour <= 4:
        # Show +2h, morning, midday, evening
        desired_entries += [("Aamu", time_now.replace(hour=8)), ("Päivä", time_now.replace(hour=13)), ("Ilta", time_now.replace(hour=19))]
    elif hour <= 10:
        # Show +2h, afternoon, evening, next morning
        desired_entries += [("Päivä", time_now.replace(hour=14)), ("Ilta", time_now.replace(hour=19)), ("Aamu", time_now.replace(hour=8) + datetime.timedelta(days=1))]
    elif hour <= 18:
        # Show +2h, evening, next morning, next afternoon
        desired_entries += [("Ilta", time_now.replace(hour=21)), ("Aamu", time_now.replace(hour=8) + datetime.timedelta(days=1)), ("Päivä", time_now.replace(hour=14) + datetime.timedelta(days=1))]
    elif hour <= 21:
        # Show +2h, night, next morning, next afternoon
        desired_entries += [("Yö", time_now.replace(hour=1) + datetime.timedelta(days=1)),  ("Aamu", time_now.replace(hour=8) + datetime.timedelta(days=1)), ("Päivä", time_now.replace(hour=14) + datetime.timedelta(days=1))]
    else:
        # Show +2h, late night, next morning, next afternoon
        desired_entries += [("Yö", time_now.replace(hour=3) + datetime.timedelta(days=1)),  ("Aamu", time_now.replace(hour=8) + datetime.timedelta(days=1)), ("Päivä", time_now.replace(hour=14) + datetime.timedelta(days=1))]
    for time_name, timestamp in desired_entries:
        for weather_item in forecast["hours"]:
            if weather_item["date"] == timestamp.date():
                if weather_item["hour"] == timestamp.hour:
                    forecast["next"].append({"name": time_name, "item": weather_item})
                    break
    forecast = json.loads(json.dumps(forecast, default=json_default))
    return forecast


class get_json(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(json.dumps(get_weather_data()), content_type="application/json")
