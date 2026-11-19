# Third-party notices

## Test fixtures

The accessory descriptions in `tests/fixtures/` are copied unchanged from the
test fixtures of the Home Assistant HomeKit Controller integration,
[`tests/components/homekit_controller/fixtures`](https://github.com/home-assistant/core/tree/dev/tests/components/homekit_controller/fixtures)
in [Home Assistant Core](https://github.com/home-assistant/core).

Copyright the Home Assistant contributors.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
these files except in compliance with the License. You may obtain a copy of the
License at <https://www.apache.org/licenses/LICENSE-2.0>.

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

## Libraries in the container image

The image installs these libraries from PyPI, unchanged, under their own
licenses:

| Library | License |
| --- | --- |
| [aiohomekit](https://github.com/Jc2k/aiohomekit) | Apache-2.0 |
| [aiomqtt](https://github.com/empicano/aiomqtt) | BSD-3-Clause |
| [paho-mqtt](https://github.com/eclipse-paho/paho.mqtt.python) | EPL-2.0 or BSD-3-Clause |
| [zeroconf](https://github.com/python-zeroconf/python-zeroconf) | LGPL-2.1-or-later |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD-3-Clause |
| [orjson](https://github.com/ijl/orjson) | MPL-2.0 and (Apache-2.0 or MIT) |

The other packages in `requirements.lock` are dependencies of these and keep
their own licenses as published on PyPI.
