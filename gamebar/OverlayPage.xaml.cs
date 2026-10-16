// Copyright (c) 2026 Sacred LLC. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Gaming.XboxGameBar;
using Microsoft.Gaming.XboxGameBar.Input;
using Windows.Data.Json;
using Windows.Storage;
using Windows.System;
using Windows.UI;
using Windows.UI.Core;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Controls.Primitives;
using Windows.UI.Xaml.Media;
using Windows.UI.Xaml.Navigation;
namespace SacredOverlay {
 public sealed class MacroCard {
  public string Kind {get;set;} public string Name {get;set;} public string Group {get;set;} public string Description {get;set;}
 }
 public sealed partial class OverlayPage : Page {
  private readonly HttpClient client=new HttpClient(new HttpClientHandler { AllowAutoRedirect=false }) {Timeout=TimeSpan.FromSeconds(3)};
  private readonly DispatcherTimer timer=new DispatcherTimer {Interval=TimeSpan.FromSeconds(1)};
  private XboxGameBarWidget widget;
  private XboxGameBarHotkeyWatcher watcher;
  private string token, endpoint, selected;
  private bool refreshing, preferencesLoaded;
  private JsonObject catalog=new JsonObject(), permissions=new JsonObject(), current=new JsonObject();
  private readonly Dictionary<string,FrameworkElement> inputs=new Dictionary<string,FrameworkElement>();
  private static readonly MacroCard[] Macros={
   new MacroCard{Kind="single_edit",Name="Single Edit",Group="EDITING",Description="Edit → select → confirm. Hold to repeat; you aim the edit."},
   new MacroCard{Kind="drag",Name="Drag Edit",Group="EDITING",Description="Hold edit to hold select. Release to stop; choose manual or automatic confirm."},
   new MacroCard{Kind="quick_reset",Name="Quick Reset",Group="EDITING",Description="Edit → reset → confirm, once per press."},
   new MacroCard{Kind="prefire",Name="Pre-fire",Group="BUILDING",Description="Shot → wall → place. Manual trigger; no opponent or timing detection."},
   new MacroCard{Kind="wall_replace",Name="Wall replace",Group="BUILDING",Description="Pickaxe → swing → wall → place. One attempt; ownership and destruction are not guaranteed."},
   new MacroCard{Kind="auto_build",Name="Auto Build",Group="BUILDING",Description="Hold a wall, stair, floor or cone bind to hold secondary place. Release all piece binds to stop."},
   new MacroCard{Kind="floor_cone",Name="Floor + Cone",Group="BUILDING",Description="Floor → place → cone → place, once per press. You aim."},
   new MacroCard{Kind="pickup",Name="Fast pickup",Group="UTILITY",Description="Hold activation to repeat interact. Game pickup limits still apply."},
   new MacroCard{Kind="mantle",Name="Mantle repeat",Group="MOVEMENT",Description="Hold activation to repeat jump/mantle. Requires a valid ledge. Does NOT prevent fall damage or guarantee survival."}
  };
  public OverlayPage() {
   InitializeComponent();Cards.ItemsSource=Macros;
   timer.Tick+=async(s,e)=>await Refresh();
   Unloaded+=(s,e)=>{timer.Stop();watcher?.Stop();};
  }
  protected override void OnNavigatedTo(NavigationEventArgs e) {
   widget=e.Parameter as XboxGameBarWidget;
   var values=ApplicationData.Current.LocalSettings.Values;
   if(values.ContainsKey("opacity")) OpacityControl.Value=Convert.ToDouble(values["opacity"]);
   if(values.ContainsKey("accent")) Accent.SelectedIndex=Convert.ToInt32(values["accent"]);
   if(values.ContainsKey("hotkey")) Hotkey.SelectedIndex=Convert.ToInt32(values["hotkey"]);
   preferencesLoaded=true;
   ConfigureHotkey();
  }
  private async Task<JsonObject> Command(string action,JsonObject payload=null) {
   if(endpoint==null) throw new InvalidOperationException("Pair the widget in the desktop app first.");
   var body=new JsonObject { ["action"]=JsonValue.CreateStringValue(action),["payload"]=payload??new JsonObject() };
   using(var req=new HttpRequestMessage(HttpMethod.Post,endpoint+"/command")) {
    req.Headers.Authorization=new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer",token);
    req.Content=new StringContent(body.Stringify(),Encoding.UTF8,"application/json");
    using(var response=await client.SendAsync(req)) {
     response.EnsureSuccessStatusCode();
     var data=JsonObject.Parse(await response.Content.ReadAsStringAsync());
     if(!data.GetNamedBoolean("ok",false)) throw new InvalidOperationException(data.GetNamedString("error","Desktop request failed."));
     return data.GetNamedObject("data");
    }
   }
  }
  private async Task Refresh() {
   if(refreshing||endpoint==null)return;refreshing=true;
   try {
    current=await Command("macro_status");catalog=current.GetNamedObject("catalog");permissions=current.GetNamedObject("permissions");
    Status.Text=(current.GetNamedBoolean("enabled",false)?"ENABLED · ":"DISABLED · ")+current.GetNamedString("reason","");
    if(selected==null)ShowFields(current.GetNamedString("kind","single_edit"));
   } catch(Exception ex) { Status.Text="Disconnected: "+ex.Message; }
   finally{refreshing=false;}
  }
  private async void Pair_Click(object sender,RoutedEventArgs e) {
   int port;
   if(!int.TryParse(Port.Text,out port)||port<1024||port>65535||PairCode.Password.Length<32){Status.Text="Enter the port and code shown by the desktop app.";return;}
   endpoint="http://127.0.0.1:"+port;token=PairCode.Password;
   await Refresh();timer.Start();
  }
  private async void Card_Click(object sender,ItemClickEventArgs e) {
   try{await Command("emergency_stop");ShowFields(((MacroCard)e.ClickedItem).Kind);}catch(Exception ex){Status.Text=ex.Message;}
  }
  private void ShowFields(string kind) {
   if(!catalog.ContainsKey(kind))return;
   selected=kind;Fields.Children.Clear();inputs.Clear();
   Description.Text=Macros.First(m=>m.Kind==kind).Description;
   var config=current.GetNamedString("kind","")==kind?current.GetNamedObject("config"):catalog.GetNamedObject(kind);
   foreach(var item in config) {
    if(kind=="auto_build"&&item.Key=="activation")continue;
    FrameworkElement input;
    if(item.Value.ValueType==JsonValueType.Boolean)input=new CheckBox{Content=item.Key.Replace('_',' '),IsChecked=item.Value.GetBoolean()};
    else if(item.Key=="confirm_mode") {var combo=new ComboBox{Header="Confirmation",ItemsSource=new[]{"manual","auto"},SelectedItem=item.Value.GetString()};input=combo;}
    else input=new TextBox{Header=item.Key.Replace('_',' '),Text=item.Value.ValueType==JsonValueType.Number?item.Value.GetNumber().ToString(System.Globalization.CultureInfo.InvariantCulture):item.Value.GetString(),MaxLength=20};
    inputs[item.Key]=input;Fields.Children.Add(input);
   }
  }
  private JsonObject ReadConfig() {
   var config=new JsonObject();
   foreach(var item in inputs) {
    if(item.Value is CheckBox)config[item.Key]=JsonValue.CreateBooleanValue(((CheckBox)item.Value).IsChecked==true);
    else if(item.Value is ComboBox)config[item.Key]=JsonValue.CreateStringValue((string)((ComboBox)item.Value).SelectedItem);
    else {var text=((TextBox)item.Value).Text.Trim();double n;
     if(item.Key.EndsWith("_ms")){if(!double.TryParse(text,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out n)||double.IsNaN(n)||double.IsInfinity(n))throw new InvalidOperationException("Enter a valid timing value.");config[item.Key]=JsonValue.CreateNumberValue(n);}
     else config[item.Key]=JsonValue.CreateStringValue(text.ToUpperInvariant());
    }
   }
   return config;
  }
  private async void Save_Click(object sender,RoutedEventArgs e) {
   try {
    if(selected==null)throw new InvalidOperationException("Choose a macro first.");
    current=await Command("macro_configure",new JsonObject{["kind"]=JsonValue.CreateStringValue(selected),["config"]=ReadConfig()});
    Status.Text="Saved. Disabled until you enable.";
   }catch(Exception ex){Status.Text=ex.Message;}
  }
  private async void Enable_Click(object sender,RoutedEventArgs e) {
   try {
    if(RiskAccepted.IsChecked!=true)throw new InvalidOperationException("Read and accept the cheat-risk warning first.");
    if(selected==null||selected!=current.GetNamedString("kind","")||!permissions.GetNamedBoolean(selected,false))throw new InvalidOperationException("Save your configuration first. An authorized license is required.");
    current=await Command("macro_enable",new JsonObject{["enabled"]=JsonValue.CreateBooleanValue(true)});Status.Text="Enabled. Return to Fortnite to use the activation bind.";
   }catch(Exception ex){Status.Text=ex.Message;}
  }
  private async void Stop_Click(object sender,RoutedEventArgs e){try{await Command("emergency_stop");Status.Text="Stopped.";}catch(Exception ex){Status.Text=ex.Message;}}
  private async void Disconnect_Click(object sender,RoutedEventArgs e){try{await Command("emergency_stop");}catch{}timer.Stop();endpoint=token=null;PairCode.Password="";selected=null;Fields.Children.Clear();Status.Text="Disconnected.";}
  private void ConfigureHotkey(){
   if(widget==null)return;
   try{watcher?.Stop();var keys=new List<VirtualKey>{Hotkey.SelectedIndex==1?VirtualKey.F9:Hotkey.SelectedIndex==2?VirtualKey.F10:VirtualKey.Tab};
    watcher=XboxGameBarHotkeyWatcher.CreateWatcher(widget,keys);
    watcher.HotkeySetStateChanged+=async(s,a)=>{if(a.HotkeySetDown)await Dispatcher.RunAsync(CoreDispatcherPriority.Normal,()=>Body.Visibility=Body.Visibility==Visibility.Visible?Visibility.Collapsed:Visibility.Visible);};watcher.Start();
   }catch(Exception ex){Status.Text="Shortcut unavailable. Use Win+G. "+ex.Message;}
  }
  private void Hotkey_Changed(object sender,SelectionChangedEventArgs e){if(Hotkey==null)return;if(preferencesLoaded)ApplicationData.Current.LocalSettings.Values["hotkey"]=Hotkey.SelectedIndex;ConfigureHotkey();}
  private void Opacity_Changed(object sender,RangeBaseValueChangedEventArgs e){if(Surface==null)return;var color=((SolidColorBrush)Surface.Background).Color;color.A=(byte)(255*e.NewValue/100);Surface.Background=new SolidColorBrush(color);if(preferencesLoaded)ApplicationData.Current.LocalSettings.Values["opacity"]=e.NewValue;}
  private void Accent_Changed(object sender,SelectionChangedEventArgs e){if(Accent==null||Cards==null)return;var color=Accent.SelectedIndex==1?Color.FromArgb(255,100,190,255):Accent.SelectedIndex==2?Color.FromArgb(255,240,202,110):Color.FromArgb(255,189,168,255);Cards.Foreground=new SolidColorBrush(color);if(preferencesLoaded)ApplicationData.Current.LocalSettings.Values["accent"]=Accent.SelectedIndex;}
 }
}
