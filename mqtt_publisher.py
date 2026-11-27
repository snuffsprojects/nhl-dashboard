"""Optional MQTT transport boundary for future companion displays."""

import json
from datetime import datetime

import paho.mqtt.client as mqtt

from config import MQTT_BROKER, MQTT_ENABLED, MQTT_PORT, MQTT_TOPIC_SCORE


def publish_mqtt(topic, payload):
    if not MQTT_ENABLED:
        return
    client = None
    loop_started = False

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        loop_started = True

        payload_str = json.dumps(payload)
        is_current_state = topic == MQTT_TOPIC_SCORE
        publish_result = client.publish(
            topic,
            payload_str,
            qos=1 if is_current_state else 0,
            retain=is_current_state,
        )
        publish_result.wait_for_publish(timeout=5)

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"📡 [MQTT BROADCAST] [{timestamp}] Topic: {topic} -> {payload_str[:80]}...")
    except Exception as error:
        print(f"\n❌ [MQTT ERROR] Broadcast failed on topic {topic}: {error}")
    finally:
        if client is not None:
            try:
                if loop_started:
                    client.loop_stop()
                client.disconnect()
            except Exception:
                pass
