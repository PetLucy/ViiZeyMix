project(
  'viizeymix',
  'c',
  version: '0.7.2',
  default_options: [
    'c_std=gnu17',
    'warning_level=2',
  ],
)

python = import('python').find_installation('python3')
prefix = get_option('prefix')
datadir = get_option('datadir')
libdir = get_option('libdir')
libexec_dir = join_paths(prefix, libdir, 'viizeymix')
app_data_dir = join_paths(prefix, datadir, 'viizeymix')

pipewire_dep = dependency('libpipewire-0.3')
threads_dep = dependency('threads')
cc = meson.get_compiler('c')
math_dep = cc.find_library('m', required: true)

executable(
  'viizeymix-backend',
  'backend/vm_backend.c',
  dependencies: [pipewire_dep],
  install: true,
  install_dir: libexec_dir,
)

executable(
  'viizeymix-dsp',
  'backend/viizeymix_dsp.c',
  'backend/intellipan_dsp.c',
  dependencies: [pipewire_dep, threads_dep, math_dep],
  install: true,
  install_dir: libexec_dir,
)

install_data(
  'src/main.py',
  'src/audio_backend.py',
  'src/effects.py',
  'src/version.py',
  install_dir: app_data_dir,
)

launcher_config = configuration_data()
launcher_config.set('PYTHON', python.full_path())
launcher_config.set('APP_DATA_DIR', app_data_dir)
launcher = configure_file(
  input: 'data/viizeymix.in',
  output: 'viizeymix',
  configuration: launcher_config,
)
install_data(
  launcher,
  install_dir: join_paths(prefix, get_option('bindir')),
  install_mode: 'rwxr-xr-x',
)

install_data(
  'data/io.github.petlucy.viizeymix.desktop',
  install_dir: join_paths(prefix, datadir, 'applications'),
)
install_data(
  'data/io.github.petlucy.viizeymix.metainfo.xml',
  install_dir: join_paths(prefix, datadir, 'metainfo'),
)
install_data(
  'data/icons/io.github.petlucy.viizeymix.svg',
  install_dir: join_paths(prefix, datadir, 'icons', 'hicolor', 'scalable', 'apps'),
)
install_data(
  'LICENSE',
  install_dir: join_paths(prefix, datadir, 'licenses', 'viizeymix'),
)

intellipan_dsp_test = executable(
  'intellipan-dsp-test',
  'tests/test_intellipan_dsp.c',
  'backend/intellipan_dsp.c',
  include_directories: include_directories('backend'),
  dependencies: [math_dep],
  install: false,
)

test('intellipan-dsp', intellipan_dsp_test)
