# agnostic

Written in [Cyrius](https://github.com/MacCracken/cyrius).

## Build

```sh
cyrius deps                              # resolve stdlib deps
cyrius build src/main.cyr build/agnostic    # compile
cyrius test                              # run [build].test + tests/*.tcyr
```

## WebGUI

`./build/agnostic` serves the WebGUI at `http://127.0.0.1:8000/ui`. Views such as Swarm Command are
compiled-in plugins that an administrator switches on in its Settings tab — see
[`docs/guides/webgui-plugins.md`](docs/guides/webgui-plugins.md).

## License

GPL-3.0-only
