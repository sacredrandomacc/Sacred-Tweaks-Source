// Copyright (c) 2026 Sacred LLC. All rights reserved.
using Microsoft.Gaming.XboxGameBar;
using Windows.ApplicationModel.Activation;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
namespace SacredOverlay {
    sealed partial class App : Application {
        private XboxGameBarWidget widget;
        public App() { InitializeComponent(); }
        protected override void OnActivated(IActivatedEventArgs args) {
            var activation = args as XboxGameBarWidgetActivatedEventArgs;
            if (activation == null || !activation.IsLaunchActivation) return;
            var frame = new Frame();
            Window.Current.Content = frame;
            widget = new XboxGameBarWidget(activation, Window.Current.CoreWindow, frame);
            frame.Navigate(typeof(OverlayPage), widget);
            Window.Current.Closed += (s,e) => { widget = null; };
            Window.Current.Activate();
        }
        protected override void OnLaunched(LaunchActivatedEventArgs args) {
            Window.Current.Content = new TextBlock { Text="Sacred Overlay is installed. Press Win+G, open Widgets, select Sacred Overlay, then pin it. Keep Sacred Tweaks running and signed in.", TextWrapping=TextWrapping.Wrap, Margin=new Thickness(32) };
            Window.Current.Activate();
        }
    }
}
