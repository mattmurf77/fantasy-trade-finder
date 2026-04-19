// Reanimated 4 requires its worklets plugin to be listed LAST in `plugins`.
// This lets the Hermes/JSC worklet compiler see every wrapped function.
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      'react-native-worklets/plugin',
    ],
  };
};
