import board
import digitalio
import time
import rtc
import busio
import adafruit_ssd1306
import adafruit_ds3231
import neopixel

class LowLevelOutputPin:
    def __init__(self, pin):
        self.pin = digitalio.DigitalInOut(pin)
        self.pin.direction = digitalio.Direction.OUTPUT
        self.pin.drive_mode = digitalio.DriveMode.PUSH_PULL

    def on(self):
        self.pin.value = False

    def off(self):
        self.pin.value = True

    def is_on(self):
        return self.pin.value == False

class InputPin:
    def __init__(self, pin):
        self.button = digitalio.DigitalInOut(pin)
        self.button.direction = digitalio.Direction.INPUT
        self.button.pull = digitalio.Pull.UP
        self.button_down = False
        self.button_pressed = False

    def tick(self):
        if self.button_down == False:
            if self.button.value == False:
                self.button_down = True
                self.button_pressed = True
        else:
            if self.button.value == True:
                self.button_down = False

    def state(self):
        state = self.button_pressed;
        self.button_pressed = False
        return state

class DayNightLed:
    SETTLE_TIME = 1
    SETTINGS_RESET_TIME = 5 * 60

    def __init__(self, pin):
        self.state = 'off'
        self.off_timestamp = time.time()
        self.pin = pin

    def _on(self):
        if self.pin.is_on():
            return
        self.state = self.next_state(self.state)
        self.pin.on()

    def _off(self):
        self.off_timestamp = time.time()
        self.pin.off()

    def next_state(self, state):
        transitions = {'off': 'day', 'day': 'evening', 'evening': 'night', 'night': 'day'}
        return transitions[state]

    def set(self, mode):
        time_diff = time.time() - self.off_timestamp
        if not self.pin.is_on() and time_diff > DayNightLed.SETTINGS_RESET_TIME:
            self.state = 'off'
        while self.state != mode:
            self._off()
            time.sleep(DayNightLed.SETTLE_TIME)
            self._on()
            time.sleep(DayNightLed.SETTLE_TIME)

    def set_day(self):
        self.set('day')

    def set_evening(self):
        self.set('evening')

    def set_night(self):
        self.set('night')

    def set_off(self):
        self._off()

    def set_next(self):
        self.state = self.next_state(self.state)

class OLED:
    def __init__(self, i2c):
        self.lines = []
        self.i2c = i2c
        self.oled = adafruit_ssd1306.SSD1306_I2C(128, 32, self.i2c)

    def display_text(self):
        row = 0
        col = 0
        for t in self.lines:
            if col > 2:
                break
            self.oled.text(t, 0, row, 1)
            row += 12
            col += 1

        self.oled.show()
        self.displaying = True

    def hide_text(self):
        self.oled.fill(0)
        self.oled.show()
        self.displaying = False

    def set_text(self, lines):
        if self.lines != lines:
            self.lines = lines
            self.hide_text()
            self.display_text()

class RTC:
    def __init__(self, i2c):
        self.i2c = i2c
        self.rtc = adafruit_ds3231.DS3231(self.i2c)

    def set_time(self, year, mon, day, hour, mnt, sec):
        self.rtc.datetime = time.struct_time((year, mon, day, hour, mnt, sec, 0, -1, -1))

    @property
    def datetime(self):
        return self.rtc.datetime

    def localtime(self):
        return self.rtc.datetime

class HW:
    def build_prepared():
        return HW.build(co2_pin = board.GP29,
                        plant_led_pin = board.GP28,
                        day_night_led_pins = (board.GP27, board.GP26),
                        i2c_pins = (board.GP15, board.GP14),
                        down_button_pin = board.GP7,
                        up_button_pin = board.GP8)

    def build(i2c_pins, co2_pin, plant_led_pin, day_night_led_pins, down_button_pin, up_button_pin):
        i2c_scl, i2c_sda = i2c_pins
        day_night_led1, day_night_led2 = day_night_led_pins
        return HW(co2_pin = co2_pin,
                  plant_led_pin = plant_led_pin,
                  day_night_led1_pin = day_night_led1, day_night_led2_pin = day_night_led2,
                  down_button_pin = down_button_pin,
                  up_button_pin = up_button_pin,
                  i2c_scl_pin = i2c_scl, i2c_sda_pin = i2c_sda)

    def __init__(self, co2_pin, plant_led_pin,
                 day_night_led1_pin, day_night_led2_pin,
                 down_button_pin, up_button_pin,
                 i2c_scl_pin, i2c_sda_pin):
        self.led = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.03)
        self.i2c = busio.I2C(i2c_scl_pin, i2c_sda_pin)
        self.rtc = RTC(self.i2c)
        rtc.set_time_source(self.rtc)
        self.oled = OLED(self.i2c)
        self.set_text(['................',
                       '..starting up...',
                       '................'])
        self.co2 = LowLevelOutputPin(co2_pin)
        self.set_co2_off()
        self.plant_led = LowLevelOutputPin(plant_led_pin)
        self.set_plant_led_off()
        self.day_night_led1 = DayNightLed(LowLevelOutputPin(day_night_led1_pin))
        self.day_night_led1.set_off()
        self.day_night_led2 = DayNightLed(LowLevelOutputPin(day_night_led2_pin))
        self.day_night_led2.set_off()
        self.down_button = InputPin(down_button_pin)
        self.up_button = InputPin(up_button_pin)

    def tick(self):
        self.up_button.tick()
        self.down_button.tick()

    def get_up_button_state(self):
        return self.up_button.state()

    def get_down_button_state(self):
        return self.down_button.state()

    def led_off(self):
        self.led.fill((0, 0, 0))

    def led_red(self):
        self.led.fill((255, 0, 0))

    def led_green(self):
        self.led.fill((0, 255, 0))

    def led_blue(self):
        self.led.fill((0, 0, 255))

    def led_yellow(self):
        self.led.fill((255, 255, 0))

    def led_cyan(self):
        self.led.fill((0, 255, 255))

    def led_white(self):
        self.led.fill((255, 255, 255))

    def led_pink(self):
        self.led.fill((255, 0, 255))

    def set_day_night_led_evening(self):
        self.day_night_led1.set_evening()
        self.day_night_led2.set_evening()

    def set_day_night_led_night(self):
        self.day_night_led1.set_night()
        self.day_night_led2.set_night()

    def set_day_night_led_day(self):
        self.day_night_led1.set_day()
        self.day_night_led2.set_day()

    def set_day_night_led_off(self):
        self.day_night_led1.set_off()
        self.day_night_led2.set_off()

    def set_day_night_led1_next_mode(self):
        self.day_night_led1.set_next()

    def set_day_night_led2_next_mode(self):
        self.day_night_led2.set_next()

    def set_plant_led_on(self):
        self.plant_led.on()

    def set_plant_led_off(self):
        self.plant_led.off()

    def set_co2_on(self):
        self.co2.on()

    def set_co2_off(self):
        self.co2.off()

    def set_text(self, text):
        print(f'OLED: {text}')
        self.oled.set_text(text)

    def time(self):
        return time.time()

    def time_of_day(self):
        t = self.rtc.localtime()
        hour = t.tm_hour
        if self.is_daylight(t.tm_mon, t.tm_mday, t.tm_wday):
            hour += 1
        return (hour * 3600 + t.tm_min * 60 + t.tm_sec) % (3600 * 24)

    def is_daylight(self, month, day, weekday):
        if month > 3 and month < 10:
            return True

        if month < 3 or month > 10:
            return False

        weekdaysAfterSwitch = {31: [6, 0, 1, 2, 3, 4, 5],
                               30: [6, 0, 1, 2, 3, 4],
                               29: [6, 0, 1, 2, 3],
                               28: [6, 0, 1, 2],
                               27: [6, 0, 1],
                               26: [6, 0],
                               25: [6]}
        if month == 3:
           if day >= 25 and weekday in weekdaysAfterSwitch[day]:
                return True
           return False

        if month == 10:
            if day >= 25 and weekday in weekdaysAfterSwitch[day]:
                return False
            return True

class Lights:
    TICK = 1
    H = 60 * 60
    H_H = 30 * 60
    M = 60

    def __init__(self, hw, schedule, self_test = False):
        self.hw = hw
        self.schedule = schedule
        if self_test == True:
            self.self_test()
        self.mode = self.get_mode(self.hw.time_of_day())
        self.act(self.mode)

    def self_test(self):
        Lights.print_current_time('Self test START')
        for end_time, color, mode in self.schedule:
            self.led_color(color)
            self.act(mode)
            time.sleep(5)
        Lights.print_current_time('Self test DONE')

    def loop(self):
        while True:
            self.hw.tick()
            self.tick()
            if self.hw.get_up_button_state():
                Lights.print_current_time('Changing LED1 mode')
                self.hw.set_day_night_led1_next_mode()
            if self.hw.get_down_button_state():
                Lights.print_current_time('Changing LED2 mode')
                self.hw.set_day_night_led2_next_mode()
            time.sleep(Lights.TICK)

    def tick(self):
        current_time = self.hw.time_of_day()
        new_mode = self.get_mode(current_time)
        if current_time % 5 == 0:
            Lights.print_current_time(f'Tick, in {self.mode} mode')
        if new_mode != self.mode:
            self.act(new_mode)
            self.mode = new_mode
        if current_time % 2:
            self.set_led_color(current_time)
        else:
            self.hw.led_off()

    def set_led_color(self, time):
        for end_time, color, mode in self.schedule:
            if time < self.to_sec(end_time):
                self.led_color(color)
                return

    def get_mode(self, time):
        for end_time, color, mode in self.schedule:
            if time < self.to_sec(end_time):
                return mode
        return {}

    def to_sec(self, time):
        h, m = time
        return h * Lights.H + m * Lights.M

    def act(self, mode):
        mode_description = self.mode_to_array(mode)
        self.hw.set_text(mode_description)
        for device, command in mode.items():
            self.set_device(device, command)

    def mode_to_array(self, mode):
        output = []
        tm = time.localtime()
        hms = [f'{tm.tm_hour:02d}  ', f'{tm.tm_min:02d}  ', f'{tm.tm_sec:02d}  ']
        for device, command in mode.items():
            output += [hms.pop(0) + device + ': ' + command]
        return output

    def print_current_time(description):
        now = time.localtime()
        print(f'{description}, Current time: {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}')

    def set_device(self, device, command):
        handlers = {'day-lights': Lights.set_day_lights,
                    'co2-valve': Lights.set_co2_valve,
                    'plant-lights': Lights.set_plant_lights}
        handlers[device](self, command)

    def set_day_lights(self, command):
        command_to_function = {'off': HW.set_day_night_led_off, 'day': HW.set_day_night_led_day,
                               'night': HW.set_day_night_led_night, 'evening': HW.set_day_night_led_evening}
        print(f'set_day_lights: {command}')
        command_to_function[command](self.hw)

    def set_co2_valve(self, command):
        command_to_function = {'off': HW.set_co2_off, 'on': HW.set_co2_on}
        print(f'set_co2_valve: {command}')
        command_to_function[command](self.hw)

    def set_plant_lights(self, command):
        command_to_function = {'off': HW.set_plant_led_off, 'on': HW.set_plant_led_on}
        print(f'set_plant_lights: {command}')
        command_to_function[command](self.hw)

    def led_color(self, color):
        color_to_function = {'red': HW.led_red, 'blue': HW.led_blue, 'cyan': HW.led_cyan,
                             'green': HW.led_green, 'pink': HW.led_pink, 'yellow': HW.led_yellow}
        print(f'led_color: {color}')
        color_to_function[color](self.hw)

if __name__ == '__main__':
    hw = HW.build_prepared()

    # schedule tuple format: (end_time, led_color, mode_directives)
    # mode directive dictionary format: {device: mode},
    # where device = 'plant_lights' | 'co2-valve',  mode: 'on' | 'off'
    # or device =  'day-lights', mode 'day' | 'night' | 'evening' | 'off'
    schedule = [(( 6, 0), 'red',    {'plant-lights': 'off', 'co2-valve': 'off', 'day-lights': 'off'}),
                (( 7, 0), 'blue',   {'plant-lights': 'off', 'co2-valve': 'off', 'day-lights': 'night'}),
                (( 8, 0), 'blue',   {'plant-lights': 'off', 'co2-valve':  'on', 'day-lights': 'night'}),
                (( 9, 0), 'cyan',   {'plant-lights': 'off', 'co2-valve':  'on', 'day-lights': 'evening'}),
                ((19, 0), 'green',  {'plant-lights':  'on', 'co2-valve':  'on', 'day-lights': 'day'}),
                ((20, 0), 'pink',   {'plant-lights': 'off', 'co2-valve': 'off', 'day-lights': 'evening'}),
                ((22, 0), 'yellow', {'plant-lights': 'off', 'co2-valve': 'off', 'day-lights': 'night'}),
                ((24, 0), 'red',    {'plant-lights': 'off', 'co2-valve': 'off', 'day-lights': 'off'})]

    l = Lights(hw, schedule, self_test = False)
    l.loop()
