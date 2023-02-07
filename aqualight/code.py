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

    def time_of_day(self):
        t = self.rtc.datetime
        hour = t.tm_hour
        if (t.tm_mon > 3 and t.tm_mon < 11) or (t.tm_mon in (3, 10) and t.tm_mday > 24):
            hour += 1
        return (hour * 3600 + t.tm_min * 60 + t.tm_sec) % (3600 * 24)

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
        self.oled.set_text(text)

    def time(self):
        return time.time()

    def time_of_day(self):
        return self.rtc.time_of_day()

class Lights:
    TICK = 1
    H = 60 * 60
    H_H = 30 * 60

    def __init__(self, hw):
        self.hw = hw
        # self.self_test()
        self.mode = self.get_mode(self.hw.time_of_day())
        self.act(self.mode)

    def self_test(self):
        Lights.print_current_time('Self test START')
        self.act('off')
        time.sleep(5)
        self.act('dawn')
        time.sleep(5)
        self.act('day')
        time.sleep(5)
        self.act('dusk')
        time.sleep(5)
        self.act('off')
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
            self.get_color(self.mode)(self.hw)
        else:
            self.hw.led_off()

    def get_color(self, mode):
        mode_to_led_color= {'dawn': HW.led_blue,
                            'day': HW.led_green, 'dusk': HW.led_pink, 'off': HW.led_red}
        return mode_to_led_color[mode]

    def get_mode(self, time):
        mode_range = [( 0,             6 * Lights.H - 1, 'off'),
                      ( 6 * Lights.H,  8 * Lights.H - 1, 'dawn'),
                      ( 8 * Lights.H, 20 * Lights.H - 1, 'day'),
                      (20 * Lights.H, 22 * Lights.H - 1, 'dusk'),
                      (22 * Lights.H, 24 * Lights.H - 1, 'off')]
        for start, end, mode in mode_range:
            if time >= start and time <= end:
                return mode
        return 'off'

    def act(self, mode):
        Lights.print_current_time(f'Executing action for {mode} mode')
        mode_to_action = {'dawn': Lights.set_dawn_mode,
                          'day': Lights.set_day_mode,
                          'dusk': Lights.set_dusk_mode,
                          'off': Lights.set_off_mode}
        mode_to_action[mode](self)

    def print_current_time(description):
        now = time.localtime()
        print(f'{description}, Current time: {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}')

    def set_dawn_mode(self):
        self.hw.set_text(['start dawn mode: co2 off', 'lights: night', 'plant: off'])
        self.day_lights_off()
        self.co2_valve_off()
        self.day_night_lights_night()
        self.hw.set_text(['dawn mode: co2 off', 'lights: night', 'plant: off'])

    def set_day_mode(self):
        self.hw.set_text(['start day mode: co2 on', 'lights: day', 'plant: on'])
        self.day_lights_on()
        self.co2_valve_on()
        self.day_night_lights_day()
        self.hw.set_text(['day mode: co2 on', 'lights: day', 'plant: on'])

    def set_dusk_mode(self):
        self.hw.set_text(['start dusk mode: co2 off', 'lights: night', 'plant: off'])
        self.day_lights_off()
        self.co2_valve_off()
        self.day_night_lights_night()
        self.hw.set_text(['dusk mode: co2 off', 'lights: night', 'plant: off'])

    def set_off_mode(self):
        self.hw.set_text(['start off mode: co2 off', 'lights: off', 'plant: off'])
        self.day_lights_off()
        self.co2_valve_off()
        self.day_night_lights_off()
        self.hw.set_text(['off mode: co2 off', 'lights: off', 'plant: off'])

    def day_night_lights_night(self):
        print('set day-night lights: night')
        self.hw.set_day_night_led_night()

    def day_night_lights_day(self):
        print('set day-night lights: day')
        self.hw.set_day_night_led_day()

    def day_night_lights_off(self):
        print('set day-night lights: off')
        self.hw.set_day_night_led_off()

    def day_lights_on(self):
        print('set day lights: on')
        self.hw.set_plant_led_on()

    def day_lights_off(self):
        print('set day lights: off')
        self.hw.set_plant_led_off()

    def co2_valve_on(self):
        print('set co2 valve: on')
        self.hw.set_co2_on()

    def co2_valve_off(self):
        print('set co2 valve: off')
        self.hw.set_co2_off()

if __name__ == '__main__':
    hw = HW.build_prepared()
    l = Lights(hw)
    l.loop()
