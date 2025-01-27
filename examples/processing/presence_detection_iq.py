import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    elif args.spi:
        client = RegSPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = PresenceDetectionProcessor(sensor_config, processing_config)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = configs.IQServiceConfig()
    config.range_interval = [0.3, 0.9]
    config.sweep_rate = 40
    config.gain = 0.7
    return config


def get_processing_config():
    return {
        "threshold": {
            "name": "Threshold",
            "value": 0.3,
            "limits": [0, 1],
            "type": float,
            "text": None,
        },
    }


class PresenceDetectionProcessor:
    def __init__(self, sensor_config, processing_config):
        self.movement_history = np.zeros(int(round(5 * sensor_config.sweep_rate)))  # 5 seconds
        self.threshold = processing_config["threshold"]["value"]

        self.a_fast_tau = 0.1
        self.a_slow_tau = 1
        self.a_move_tau = 1
        self.a_fast = self.alpha(self.a_fast_tau, 1.0/sensor_config.sweep_rate)
        self.a_slow = self.alpha(self.a_slow_tau, 1.0/sensor_config.sweep_rate)
        self.a_move = self.alpha(self.a_move_tau, 1.0/sensor_config.sweep_rate)

        self.sweep_lp_fast = None
        self.sweep_lp_slow = None
        self.movement_lp = 0

        self.sweep_index = 0

    def process(self, sweep):
        if self.sweep_index == 0:
            self.sweep_lp_fast = np.array(sweep)
            self.sweep_lp_slow = np.array(sweep)
        else:
            self.sweep_lp_fast = self.sweep_lp_fast*self.a_fast + sweep*(1-self.a_fast)
            self.sweep_lp_slow = self.sweep_lp_slow*self.a_slow + sweep*(1-self.a_slow)

            movement = np.mean(np.abs(self.sweep_lp_fast - self.sweep_lp_slow))
            movement *= 100
            self.movement_lp = self.movement_lp*self.a_move + movement*(1-self.a_move)

            self.movement_history = np.roll(self.movement_history, -1)
            self.movement_history[-1] = self.movement_lp

        move_hist = np.tanh(self.movement_history)
        presence = move_hist[-1] > self.threshold

        out_data = {
            "envelope": np.abs(self.sweep_lp_fast),
            "movement_history": move_hist,
            "presence": presence,
        }

        self.sweep_index += 1
        return out_data

    def alpha(self, tau, dt):
        return np.exp(-dt/tau)


class PGUpdater:
    def __init__(self, sensor_config, processing_config):
        self.sensor_config = sensor_config
        self.threshold = processing_config["threshold"]["value"]

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        self.env_plot = win.addPlot(title="IQ amplitude")
        self.env_plot.showGrid(x=True, y=True)
        self.env_plot.setLabel("bottom", "Depth (m)")
        self.env_curve = self.env_plot.plot(pen=example_utils.pg_pen_cycler(0))
        self.env_smooth_max = example_utils.SmoothMax(self.sensor_config.sweep_rate)

        win.nextRow()
        move_hist_plot = win.addPlot(title="Movement history")
        move_hist_plot.showGrid(x=True, y=True)
        move_hist_plot.setLabel("bottom", "Time(s)")
        move_hist_plot.setXRange(-5, 0)
        move_hist_plot.setYRange(0, 1)
        self.move_hist_curve = move_hist_plot.plot(pen=example_utils.pg_pen_cycler(0))
        limit_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)
        self.limit_line = pg.InfiniteLine(self.threshold, angle=0, pen=limit_pen)
        move_hist_plot.addItem(self.limit_line)

        present_text = '<div style="text-align: center">' \
                       '<span style="color: #FFFFFF;font-size:16pt;">' \
                       '{}</span></div>'.format("Presence detected!")
        not_present_text = '<div style="text-align: center">' \
                           '<span style="color: #FFFFFF;font-size:16pt;">' \
                           '{}</span></div>'.format("No presence detected")

        self.present_text_item = pg.TextItem(
            html=present_text,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
            )
        self.not_present_text_item = pg.TextItem(
            html=not_present_text,
            fill=pg.mkColor("b"),
            anchor=(0.5, 0),
            )
        self.present_text_item.setPos(-2.5, 0.95)
        self.not_present_text_item.setPos(-2.5, 0.95)
        move_hist_plot.addItem(self.present_text_item)
        move_hist_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()

    def update(self, data):
        env_ys = data["envelope"]
        env_xs = np.linspace(*self.sensor_config.range_interval, len(env_ys))
        self.env_curve.setData(env_xs, env_ys)
        self.env_plot.setYRange(0, self.env_smooth_max.update(np.amax(env_ys)))

        move_hist_ys = data["movement_history"]
        move_hist_xs = np.linspace(-5, 0, len(move_hist_ys))
        self.move_hist_curve.setData(move_hist_xs, move_hist_ys)

        if data["presence"]:
            self.present_text_item.show()
            self.not_present_text_item.hide()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()


if __name__ == "__main__":
    main()
