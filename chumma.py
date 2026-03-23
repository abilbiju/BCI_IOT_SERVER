from pybooklid import LidSensor

# Manual connection management
sensor = LidSensor(auto_connect=False)
try:
    sensor.connect()
    
    # Wait for significant movement
    new_angle = sensor.wait_for_change(threshold=5.0, timeout=10.0)
    if new_angle:
        print(f"Lid moved to {new_angle:.1f}°")
    
    # Monitor with callback
    def on_angle_change(angle):
        print(f"Callback: {angle:.1f}°")
    
    for angle in sensor.monitor(callback=on_angle_change, max_duration=30):
        # Process angle data
        pass
        
finally:
    sensor.disconnect()