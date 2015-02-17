from .models import LightGroup, LightAutomation
from display.views import run_display_command
from django.conf import settings
from django.core import serializers
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.utils.timezone import now
from django.views.generic import View
from ledcontroller import LedController
import datetime
import json
import redis
import time

redis_instance = redis.StrictRedis()
led = LedController(settings.MILIGHT_IP)

def update_lightstate(group, brightness, color, on=True):
    if group == 0:
        for a in range(1, 5):
            update_lightstate(a, brightness, color)

    (state, _) = LightGroup.objects.get_or_create(group_id=group)
    if brightness is not None:
        if color == "white":
            state.white_brightness = brightness
        else:
            state.rgb_brightness = brightness
    if color is not None:
        state.color = color
    state.on = on
    state.save()
    return state

class timed(View):
    def post(self, request, *args, **kwargs):
        action = kwargs.get("action")
        command = kwargs.get("command")
        if command == "update":
            start_time = request.POST.get("start_time").split(":")
            duration = request.POST.get("duration").replace("+", "").split(":")
            running = request.POST.get("running")
            if running == "true":
                running = True
            else:
                running = False
            start_time = datetime.time(int(start_time[0]), int(start_time[1]))
            duration = int(duration[0]) * 3600 + int(duration[1]) * 60
            item, created = LightAutomation.objects.get_or_create(action=action, defaults={"start_time": start_time, "duration": duration, "running": running})
            if not created:
                item.start_time = start_time
                item.duration = duration
                item.running = running

            item.save()
            redis_instance.publish("home:broadcast:lightcontrol_timed", item.action)
        else:
            item = get_object_or_404(LightAutomation, action=action)
        ret = json.loads(serializers.serialize("json", [item]))
        ret[0]["fields"]["is_active"] = item.is_active_today(now())
        return HttpResponse(json.dumps(ret), content_type="application/json")


    def get(self, request, *args, **kwargs):
        action = kwargs.get("action")
        command = kwargs.get("command")
        item = get_object_or_404(LightAutomation, action=action)
        ret = json.loads(serializers.serialize("json", [item]))
        ret[0]["fields"]["is_active"] = item.is_active_today(now())
        return HttpResponse(json.dumps(ret), content_type="application/json")

class control_per_source(View):
    BED = 1
    TABLE = 2
    KITCHEN = 3
    DOOR = 4

    def get(self, request, *args, **kwargs):
        source = kwargs.get("source")
        command = kwargs.get("command")
        if source == "computer":
            if command == "night":
                led.set_brightness(0)
                led.set_color("red")
                led.set_brightness(0)
            elif command == "morning-sleeping":
                led.off()
                led.white(self.KITCHEN)
                led.set_brightness(10, self.KITCHEN)
                led.white(self.DOOR)
                led.set_brightness(10, self.DOOR)
                led.set_color("red", self.TABLE)
                led.set_brightness(0, self.TABLE)
            elif command == "morning-wakeup":
                #TODO: fade up slowly
                led.white()
                run_display_command("on")
                redis_instance.publish("home:broadcast:shutdown", "shutdown_cancel")
                for a in range(0, 100, 5):
                    led.set_brightness(a)
                    time.sleep(0.5)

            elif command == "off":
                led.set_brightness(0)
                led.off()
                redis_instance.publish("home:broadcast:shutdown", "shutdown_delay")
            elif command == "on":
                run_display_command("on")
                redis_instance.publish("home:broadcast:shutdown", "shutdown_cancel")
                led.white()
                led.set_brightness(100)
        elif source == "door":
            if command == "night":
                led.off()
                for group in (self.DOOR, self.KITCHEN):
                    led.set_color("red", group)
                    led.set_brightness(10, group)
            elif command == "morning":
                led.off(self.BED)
                for group in (self.TABLE, self.KITCHEN, self.DOOR):
                    led.set_color("white", group)
                    led.set_brightness(10, group)
            elif command == "on":
                led.white()
                led.set_brightness(100)
                run_display_command("on")
                redis_instance.publish("home:broadcast:shutdown", "shutdown_cancel")
            elif command == "off":
                led.set_brightness(0)
                led.off()
                led.white(self.DOOR)
                led.set_brightness(10, self.DOOR)
                redis_instance.publish("home:broadcast:shutdown", "shutdown_delay")
        elif source == "display":
            if command == "night":
                led.set_brightness(0)
                led.set_color("red")
                led.set_brightness(0)
            elif command == "morning-sleeping":
                led.off()
                led.white(self.KITCHEN)
                led.set_brightness(10, self.KITCHEN)
                led.white(self.DOOR)
                led.set_brightness(10, self.DOOR)
                led.set_color("red", self.TABLE)
                led.set_brightness(0, self.TABLE)
            elif command == "morning-all":
                led.white()
                led.set_brightness(30)
            elif command == "off":
                led.set_brightness(0)
                led.off()
                redis_instance.publish("home:broadcast:shutdown", "shutdown_delay")
            elif command == "on":
                redis_instance.publish("home:broadcast:shutdown", "shutdown_cancel")
                led.white()
                led.set_brightness(100)
        else:
            raise NotImplementedError("Invalid source: %s" % source)
        return HttpResponse("ok")


class control(View):
    def get(self, request, *args, **kwargs):
        command = kwargs.get("command")
        group = int(kwargs.get("group"))

        if command == "on":
            led.white(group)
            led.set_brightness(100, group)
            update_lightstate(group, 100, "white")
        elif command == "off":
            led.set_brightness(0, group)
            led.off(group)
            update_lightstate(group, None, None, False)
        elif command == "morning":
            led.white(group)
            led.set_brightness(10, group)
            update_lightstate(group, 10, "white")
        elif command == "disco":
            led.disco(group)
            update_lightstate(group, None, "disco")
        elif command == "night":
            (state, _) = LightGroup.objects.get_or_create(group_id=group)
            if state.color != "red":
                led.set_brightness(0, group)
                led.white(group)
                led.set_brightness(0, group)
            led.set_color("red", group)
            led.set_brightness(0, group)
            update_lightstate(group, 0, "red")
        else:
            raise NotImplementedError("Invalid command: %s" % command)
        return HttpResponse("ok")
