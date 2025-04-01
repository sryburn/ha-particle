import aiohttp
import asyncio
import json
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.core_config import Config
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN, CONF_ACCESS_TOKEN, CONF_DEVICES
from aiohttp import ClientTimeout

_LOGGER = logging.getLogger(__name__)

# Define service schema
SERVICE_SCHEMA = vol.Schema({
    vol.Optional('argument'): cv.string,
})

async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    # Basic error checking
    if DOMAIN not in config:
        _LOGGER.error("Particle domain not found in configuration")
        return False
        
    conf = config.get(DOMAIN, {})
    access_token = conf.get(CONF_ACCESS_TOKEN)
    devices = conf.get(CONF_DEVICES, [])
    
    if not access_token or not devices:
        _LOGGER.error("Missing access_token or devices in Particle configuration")
        return False

    session = async_get_clientsession(hass)
    
    async def fetch_device_functions(device_id):
        """Fetch the functions available on a Particle device."""
        url = f"https://api.particle.io/v1/devices/{device_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('functions', [])
            else:
                _LOGGER.error(f"Error fetching functions for device {device_id}: {response.status}")
                return []
                
    async def create_service_handler(device_id, function_name):
        """Create a service handler with device_id and function_name bound."""
        async def service_handler(service: ServiceCall):
            argument = service.data.get('argument')
            await call_particle_function(device_id, function_name, argument)
        
        return service_handler                

    async def call_particle_function(device_id, function_name, argument):
        """Call a Particle function on a device."""
        url = f"https://api.particle.io/v1/devices/{device_id}/{function_name}"
        headers = {"Authorization": f"Bearer {access_token}"}
        data = {"arg": argument if argument is not None else ""}

        try:
            async with session.post(url, headers=headers, data=data) as response:
                if response.status == 200:
                    _LOGGER.info(f"Successfully called function {function_name} on {device_id}")
                    return True
                else:
                    response_text = await response.text()
                    _LOGGER.error(f"Error calling function {function_name} on {device_id}: {response.status}, {response_text}")
                    return False
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Connection error calling function {function_name} on {device_id}: {e}")
            return False

    event_tasks = {}
    
    async def event_listener(device_id, event_name):
        task_key = f"{device_id}_{event_name}"
        if task_key in event_tasks:
            _LOGGER.warning(f"Particle {task_key}: Already running")
            return
            
        event_tasks[task_key] = True
        
        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {access_token}"
        }
        event_url = f"https://api.particle.io/v1/devices/{device_id}/events/{event_name}"
        timeout = ClientTimeout(total=None)
        
        while True:
            try:
                async with session.get(event_url, headers=headers, timeout=timeout) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error connecting to Particle.io for device {device_id}, event {event_name}: {response.status}")
                        await asyncio.sleep(60)
                        continue

                    _LOGGER.info(f"Connected to Particle.io event stream for device {device_id}, event {event_name}.")
                    buffer = b""
                    
                    async for chunk in response.content.iter_chunked(1024):
                        buffer += chunk
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            if line.startswith(b'data:'):
                                try:
                                    parsed_line = line.decode().strip().split("data: ", 1)[1]
                                    data = json.loads(parsed_line)
                                    # Customized event type to include device_id for uniqueness
                                    hass.bus.async_fire(f"particle_{device_id}_{event_name}", data)
                                except Exception as e:
                                    _LOGGER.error(f"Error processing event for device {device_id}, {event_name}: {e}")
                                    
            except asyncio.CancelledError:
                break
            except aiohttp.ClientPayloadError as e:
                _LOGGER.error(f"Payload error with Particle.io event stream for device {device_id}, event {event_name}: {e}")
            except Exception as e:
                _LOGGER.error(f"Error with Particle.io event stream for device {device_id}, event {event_name}: {e}")
    
            _LOGGER.info(f"Attempting to reconnect to Particle.io event stream for device {device_id}, event {event_name}.")
            await asyncio.sleep(60)
        
        # Clean up task tracking
        if task_key in event_tasks:
            del event_tasks[task_key]

    try:
        for device in devices:
            device_id = device.get('device_id')
            if not device_id:
                _LOGGER.error("Device missing device_id in configuration")
                continue
                
            functions = await fetch_device_functions(device_id)
            
            for function_name in functions:
                service_name = f"{device_id}_{function_name}"
                hass.services.async_register(
                    DOMAIN, 
                    service_name, 
                    await create_service_handler(device_id, function_name),
                    schema=SERVICE_SCHEMA
                )

            for event_name in device.get('events', []):
                hass.loop.create_task(event_listener(device_id, event_name))
    except Exception as e:
        _LOGGER.error(f"Error setting up Particle device: {e}")
        # Keep going, as we might have more devices to configure
    
    return True