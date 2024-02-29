# ha-particle
A simple Home Assistant component for Particle.io devices. 

This component allows you to specify a list of [Particle.publish()](https://docs.particle.io/reference/device-os/api/cloud-functions/particle-publish/) events to subscribe to and exposes them as events in Home Assistant. Additionally any [Particle.function()](https://docs.particle.io/reference/device-os/api/cloud-functions/particle-function/) methods will be automatically exposed as services which you can call in Home Assistant.

## To install
1. Copy the `particle` folder to `config\custom_components` in Home Assistant.
1. Add a configuration entry to your `configuration.yaml` file per the following example:
      ```yaml
      particle:
        access_token: YOUR_PARTICLE_ACCESS_TOKEN
        devices:
          - device_id: electron1 #ID or name of your particle device
            events: # List of particle.publish events to listen for
              - buttonpress 
              - temperature
      ```
1. Restart Home Assistant.

Particle publish events will be exposed on the Home Assistant event bus as `particle_{device_id}_{event}` eg `particle_electron1_temperature`

Particle functions will be available in Home Assistant as `particle.{device_id}_{function}` eg particle.electron1_checktemp

## Obtaining an access token
see: https://docs.particle.io/reference/cloud-apis/access-tokens/#getting-a-user-access-token
