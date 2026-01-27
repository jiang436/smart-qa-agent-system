<script setup lang="ts">
import { ref } from 'vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const activeCategory = ref('清洁刷组')

const catalog: Record<string, { name: string; model: string; price: number; life: number; desc: string }[]> = {
  '清洁刷组': [
    { name: '原装边刷', model: 'X30-SB-01', price: 29.9, life: 120, desc: '3-6个月更换，缠绕头发易炸毛' },
    { name: '原装主滚刷', model: 'X30-MB-01', price: 59.0, life: 180, desc: '地毯家庭4-8个月更换' },
  ],
  '拖地配套': [
    { name: '水洗拖布(3片)', model: 'X30-MP-01', price: 25.0, life: 60, desc: '干硬掉毛后留水渍' },
    { name: '一次性免洗拖布(30片)', model: 'X30-DM-01', price: 19.9, life: 30, desc: '用完即弃' },
    { name: '专用清洁液(500ml)', model: 'X30-CL-01', price: 39.0, life: 90, desc: '除油污地板抑菌' },
  ],
  '集尘过滤': [
    { name: '自动集尘袋(3只)', model: 'X30-DB-02', price: 49.0, life: 75, desc: '满袋吸力下降' },
    { name: 'HEPA滤芯滤网', model: 'X30-HF-01', price: 39.0, life: 180, desc: '堵塞灰尘回流异味' },
  ],
  '基站养护': [
    { name: '基站清洗盘', model: 'X30-BC-01', price: 79.0, life: 365, desc: '延长基站寿命' },
    { name: '银离子抑菌模块', model: 'X30-AG-01', price: 49.0, life: 180, desc: '抑制水箱细菌' },
    { name: '阻垢剂', model: 'X30-AS-01', price: 29.0, life: 90, desc: '防水管水垢堵塞' },
  ],
  '故障备件': [
    { name: '充电触点', model: 'X30-CT-01', price: 19.0, life: 0, desc: '氧化无法充电时更换' },
    { name: '充电底座', model: 'X30-CD-01', price: 129.0, life: 0, desc: '底座损坏时更换' },
    { name: '驱动轮', model: 'X30-DW-01', price: 79.0, life: 0, desc: '卡顿打滑时更换' },
    { name: '万向轮', model: 'X30-OW-01', price: 29.0, life: 0, desc: '原地打转时检查' },
    { name: '传感器保护盖', model: 'X30-SC-01', price: 15.0, life: 0, desc: '刮花影响感应' },
    { name: '滚刷盖板+卡扣', model: 'X30-RC-01', price: 12.0, life: 0, desc: '松动导致异响' },
    { name: '防水胶条', model: 'X30-WS-01', price: 9.0, life: 0, desc: '水箱密封老化' },
    { name: '清水箱', model: 'X30-WT-01', price: 89.0, life: 0, desc: '漏水损坏时更换' },
  ],
  '套装优惠': [
    { name: '基础清洁套装', model: 'X30-KIT-B', price: 79.9, life: 0, desc: '边刷x2+滤网+拖布x3 省¥14' },
    { name: '深度清洁套装', model: 'X30-KIT-D', price: 199.0, life: 0, desc: '边刷x2+滚刷+滤网x2+拖布+清洁液 省¥38' },
    { name: '基站养护套装', model: 'X30-KIT-S', price: 99.0, life: 0, desc: '集尘袋x3+银离子+阻垢剂 省¥28' },
  ],
}

const categories = Object.keys(catalog)
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center px-5 py-3 bg-white border-b border-slate-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-slate-800">X30 Pro 耗材配件</h1>
        <p class="text-[11px] text-slate-400">全部42款配件 · 原厂质量保证</p>
      </div>
    </header>

    <div class="flex-1 overflow-hidden flex">
      <!-- Category sidebar -->
      <aside class="w-28 bg-bg-secondary border-r border-slate-200 overflow-y-auto shrink-0 py-2">
        <button
          v-for="cat in categories" :key="cat"
          @click="activeCategory = cat"
          :class="[
            'w-full text-left px-3 py-2 text-xs transition-colors',
            activeCategory === cat ? 'bg-white text-accent font-medium' : 'text-slate-500 hover:text-slate-700'
          ]"
        >{{ cat }}</button>
      </aside>

      <!-- Product grid -->
      <div class="flex-1 overflow-y-auto p-4">
        <div class="grid grid-cols-2 gap-3">
          <div
            v-for="item in catalog[activeCategory]" :key="item.model"
            class="bg-white border border-slate-200 rounded-lg p-3 hover:border-accent/50 transition-colors"
          >
            <div class="text-xs font-medium text-slate-800 mb-0.5">{{ item.name }}</div>
            <div class="text-[10px] text-slate-400 font-mono mb-2">{{ item.model }}</div>
            <div class="text-[11px] text-slate-500 mb-2">{{ item.desc }}</div>
            <div class="flex items-center justify-between">
              <span class="text-sm font-bold text-slate-800">¥{{ item.price }}</span>
              <span v-if="item.life > 0" class="text-[10px] text-slate-400">约{{ item.life }}天</span>
            </div>
          </div>
        </div>
        <div v-if="catalog[activeCategory].length === 0" class="text-center text-slate-400 text-sm py-12">
          暂无该类别配件
        </div>
      </div>
    </div>
  </div>
</template>
