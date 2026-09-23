import appConfig from '../../../app.json';

describe('Expo configuration', () => {
  it('uses the supported SDK 57 scene lifecycle opt-in for Xcode 27', () => {
    const scenePlugin = appConfig.expo.plugins.find(
      (plugin): plugin is [string, { ios: { enableSceneSupport: boolean } }] => Array.isArray(plugin) && plugin[0] === 'expo-build-properties',
    );

    expect(scenePlugin?.[1].ios.enableSceneSupport).toBe(true);
    expect(appConfig.expo.ios).not.toHaveProperty('infoPlist.UIApplicationSceneManifest');
  });
});
