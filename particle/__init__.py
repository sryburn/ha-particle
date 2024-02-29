import aiohttp
import asyncio
import json
import logging

from homeassistant.core import HomeAssistant, Config, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_ACCESS_TOKEN, CONF_DEVICES
from aiohttp import ClientTimeout

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    conf = config[DOMAIN]
    access_token = conf[CONF_ACCESS_TOKEN]
    devices = conf[CONF_DEVICES]

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
        data = {"arg": argument}

        async with session.post(url, headers=headers, data=data) as response:
            if response.status == 200:
                _LOGGER.info(f"Successfully called function {function_name} on {device_id}")
            else:
                _LOGGER.error(f"Error calling function {function_name} on {device_id}: {response.status}")

    async def event_listener(device_id, event_name):
        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {access_token}"  # Use the Authorization header
        }
        event_url = f"https://api.particle.io/v1/devices/{device_id}/events/{event_name}"
        timeout = ClientTimeout(total=None)
        
        while True:
            try:
                async with session.get(event_url, headers=headers, timeout=timeout) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error connecting to Particle.io for device {device_id}, event {event_name}: {response.status}")
                        break

                    _LOGGER.info(f"Connected to Particle.io event stream for device {device_id}, event {event_name}.")
                    async for line in response.content:
                        if line.startswith(b'data:'):
                            try:
                                parsed_line = line.decode().strip().split("data: ", 1)[1]
                                data = json.loads(parsed_line)
                                # Customized event type to include device_id for uniqueness
                                hass.bus.async_fire(f"particle_{device_id}_{event_name}", data)
                            except Exception as e:
                                _LOGGER.error(f"Error processing event for device {device_id}, {event_name}: {e}")
                                
            except Exception as e:
                _LOGGER.error(f"Error with Particle.io event stream for device {device_id}, event {event_name}: {e}")
    
            _LOGGER.info(f"Attempting to reconnect to Particle.io event stream for device {device_id}, event {event_name}.")
            await asyncio.sleep(60)

    for device in devices:
        device_id = device['device_id']
        functions = await fetch_device_functions(device_id)
        
        for function_name in functions:
            service_name = f"{device_id}_{function_name}"
            hass.services.async_register(DOMAIN, service_name, await create_service_handler(device_id, function_name))

        for event_name in device['events']:
            hass.loop.create_task(event_listener(device_id, event_name))

    return True
