print("Napowietrzacz")

import board
import digitalio

def napowietrzacz():
    nap = digitalio.DigitalInOut(board.GP0)
    nap.switch_to_output(value=True)
    n = 0
    timeout = 0
    on_off = [105, 800]
    while True:
        n += 1
        if n == on_off[timeout % 2]:
            print(f'Switching {n} -> {(timeout % 2) == 0}')
            n = 0
            timeout += 1
            nap.switch_to_output(value=((timeout % 2) == 0))

if __name__ == '__main__':
    napowietrzacz()
