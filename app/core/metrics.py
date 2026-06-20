import threading
from typing import Dict, Tuple

class PrometheusRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # We store counters and gauges
        self.counters: Dict[str, Dict[Tuple[Tuple[str, str], ...], int]] = {
            "mpesa_stk_requests_total": {},
            "mpesa_callbacks_total": {},
            "mpesa_websocket_connections_total": {},
            "mpesa_websocket_errors_total": {},
        }
        self.gauges: Dict[str, Dict[Tuple[Tuple[str, str], ...], float]] = {
            "mpesa_websocket_active_connections": {},
        }
        self.descriptions = {
            "mpesa_stk_requests_total": "Total number of M-Pesa STK push requests initiated.",
            "mpesa_callbacks_total": "Total number of M-Pesa callback webhooks received.",
            "mpesa_websocket_connections_total": "Total number of M-Pesa WebSocket connections opened.",
            "mpesa_websocket_errors_total": "Total number of M-Pesa WebSocket processing errors.",
            "mpesa_websocket_active_connections": "Current number of active M-Pesa WebSocket connections.",
        }
        self.types = {
            "mpesa_stk_requests_total": "counter",
            "mpesa_callbacks_total": "counter",
            "mpesa_websocket_connections_total": "counter",
            "mpesa_websocket_errors_total": "counter",
            "mpesa_websocket_active_connections": "gauge",
        }

    def increment_counter(self, name: str, labels: Dict[str, str] = None, value: int = 1) -> None:
        with self._lock:
            if name not in self.counters:
                self.counters[name] = {}
            lbl_tuple = tuple(sorted(labels.items())) if labels else ()
            self.counters[name][lbl_tuple] = self.counters[name].get(lbl_tuple, 0) + value

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None) -> None:
        with self._lock:
            if name not in self.gauges:
                self.gauges[name] = {}
            lbl_tuple = tuple(sorted(labels.items())) if labels else ()
            self.gauges[name][lbl_tuple] = value

    def adjust_gauge(self, name: str, delta: float, labels: Dict[str, str] = None) -> None:
        with self._lock:
            if name not in self.gauges:
                self.gauges[name] = {}
            lbl_tuple = tuple(sorted(labels.items())) if labels else ()
            self.gauges[name][lbl_tuple] = self.gauges[name].get(lbl_tuple, 0.0) + delta

    def generate_metrics_text(self) -> str:
        lines = []
        with self._lock:
            # Process counters
            for name, label_dict in self.counters.items():
                desc = self.descriptions.get(name, "")
                metric_type = self.types.get(name, "counter")
                lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} {metric_type}")
                for lbl_tuple, val in label_dict.items():
                    if lbl_tuple:
                        lbl_str = ",".join(f'{k}="{v}"' for k, v in lbl_tuple)
                        lines.append(f"{name}{{{lbl_str}}} {val}")
                    else:
                        lines.append(f"{name} {val}")
                lines.append("")
            
            # Process gauges
            for name, label_dict in self.gauges.items():
                desc = self.descriptions.get(name, "")
                metric_type = self.types.get(name, "gauge")
                lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} {metric_type}")
                for lbl_tuple, val in label_dict.items():
                    if lbl_tuple:
                        lbl_str = ",".join(f'{k}="{v}"' for k, v in lbl_tuple)
                        lines.append(f"{name}{{{lbl_str}}} {val}")
                    else:
                        lines.append(f"{name} {val}")
                lines.append("")

        return "\n".join(lines)

metrics_registry = PrometheusRegistry()
