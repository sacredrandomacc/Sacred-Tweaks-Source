'use strict';
// Shared by the main app and the companion overlay.
// [name, accent, second glow, surface, text, supporting text, optional 'special' badge]
  // Curated dark palettes: [name, accent, second glow, surface, text, supporting text].
window.SacredThemes = Object.freeze({
    'sacred-violet':['Sacred Violet','#9A82F7','#5B7CFA','#111318','#F2F0EA','#AAA9AD'],
    'sacred-blue':['Sacred Blue','#1E90FF','#38BDF8','#0A1220','#EAF2FF','#93A7C4'],
    'midnight':['Midnight','#7C8CFF','#4CC2FF','#0E1220','#EEF1FA','#A3AAC2'],
    'cobalt':['Cobalt','#3D8BFF','#22D3EE','#0C1424','#EAF2FF','#9DB0CC'],
    'arctic':['Arctic','#7DD3FC','#A5B4FC','#0F171D','#EFF8FC','#A2B6C2'],
    'aqua':['Aqua','#22D3EE','#34D399','#0B1719','#E8FAFB','#9DBDC0'],
    'teal':['Deep Teal','#2DD4BF','#38BDF8','#0C1615','#E9F7F4','#9EBAB5'],
    'emerald':['Emerald','#34D399','#A3E635','#0D1511','#EAF6EF','#A0B8AA'],
    'forest':['Forest','#86C06C','#E5C07B','#11150F','#EEF2E8','#A9B39F'],
    'lime':['Volt','#B5F23D','#34D399','#111410','#F1F6E9','#AAB39C'],
    'gold':['Gold Rush','#F2C14E','#F59E0B','#15130D','#F7F2E6','#B8AF9A'],
    'amber':['Amber','#FFA94D','#F2C14E','#16110C','#F8F0E7','#BBAA98'],
    'sunset':['Sunset','#FF7A59','#F472B6','#171010','#FBEFEA','#BFA59E'],
    'crimson':['Crimson','#F43F5E','#FB923C','#160D10','#FBECEF','#BE9EA6'],
    'rose':['Rose','#FB7185','#C084FC','#170F13','#FBEEF2','#BEA2AD'],
    'sakura':['Sakura','#F9A8D4','#C4B5FD','#161015','#FBF0F6','#BDA6B5'],
    'magenta':['Magenta','#E879F9','#818CF8','#140E18','#F8EEFB','#B7A2BF'],
    'lavender':['Lavender','#C4B5FD','#93C5FD','#13121A','#F2F0FA','#ABA8BD'],
    'dracula':['Dracula','#BD93F9','#FF79C6','#1A1B26','#F8F8F2','#A9ADC6'],
    'nord':['Nord','#88C0D0','#81A1C1','#1B2028','#ECEFF4','#A7B0C0'],
    'mocha':['Mocha','#CBA6F7','#F5C2E7','#181825','#CDD6F4','#A6ADC8'],
    'solar':['Solar','#B58900','#2AA198','#0A1C22','#EEE8D5','#93A1A1'],
    'graphite':['Graphite','#D4D4D8','#A1A1AA','#121214','#F4F4F5','#A1A1AA'],
    'obsidian':['Obsidian','#FFFFFF','#9CA3AF','#060607','#FAFAFA','#9B9BA1'],
    'neon':['Neon Night','#00F5D4','#F15BB5','#0B0B14','#F1F1FA','#A3A3BF'],
    'abyss':['Abyss','#2EC4B6','#3A86FF','#071216','#E6F6F5','#93B3B2'],
    'synthwave':['Synthwave','#FF2E97','#00E5FF','#140B22','#FBEFFF','#B9A3C9'],
    'ruby':['Ruby','#E0115F','#FF6B6B','#140A0E','#FBEAF0','#BE9CA9'],
    'mint':['Mint Ice','#5EEAD4','#A7F3D0','#0D1514','#ECFBF7','#A2BDB7'],
    'coffee':['Espresso','#C8A27A','#E6B980','#14100D','#F4ECE4','#B4A595'],
    'toxic':['Toxic','#39FF14','#00FFA3','#0A100A','#ECFBE8','#9FB89A'],
    'contrast':['High Contrast','#FFD400','#FFFFFF','#000000','#FFFFFF','#E6E6E6'],
    'cb-blue-orange':['Colour-safe: Blue / Orange','#3B82F6','#F59E0B','#0B1220','#F4F6FA','#B8C0CC'],
    'cb-teal-red':['Colour-safe: Teal / Red','#14B8A6','#EF4444','#0D1414','#F2F7F6','#A9BDB9'],
    'halloween':['Halloween','#FF7518','#9D4EDD','#0E0A12','#F8EEE6','#B9A7B6','special'],
    'winter':['Winterfrost','#9AD9FF','#E0F2FE','#0B1320','#F1F8FF','#A5B7CB','special'],
    'lunar':['Lunar New Year','#FF3B3B','#FFC94A','#160A0A','#FFF1E8','#C7A69C','special'],
    'summer':['Summer Splash','#FFB703','#00C2D1','#0B1A1F','#FFF8E7','#A9BEC2','special']
  });

// Interface fonts: [label, CSS stack]. Only fonts Windows ships; nothing downloads.
window.SacredFonts = Object.freeze({system:['System (Segoe UI)','"Segoe UI Variable","Segoe UI",Inter,Arial,sans-serif'],bahnschrift:['Bahnschrift','Bahnschrift,"Segoe UI",sans-serif'],cascadia:['Cascadia Code','"Cascadia Code","Cascadia Mono",Consolas,monospace'],trebuchet:['Trebuchet','"Trebuchet MS","Segoe UI",sans-serif'],georgia:['Georgia','Georgia,"Times New Roman",serif'],verdana:['Verdana','Verdana,"Segoe UI",sans-serif'],franklin:['Franklin Gothic','"Franklin Gothic Medium","Arial Narrow",sans-serif']});

// Special themes unlock during their season (0-based months). Out of season they show as locked.
window.SacredSeasons = Object.freeze({halloween:[9], winter:[11,0,1], lunar:[0,1], summer:[5,6,7]});
window.SacredSeasonOpen = id => { const months = window.SacredSeasons[id]; return !months || months.includes(new Date().getMonth()); };
