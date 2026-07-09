import { writeFileSync, mkdirSync } from 'fs'
import { join } from 'path'
import { DEMO_PERIODS, DEMO_REPORT, DEMO_DOCUMENTS, DEMO_PROFILE } from '../src/demo/demoData'

const outputDir = join(process.cwd(), 'dist-temp')
mkdirSync(outputDir, { recursive: true })

writeFileSync(join(outputDir, 'demo_periods.json'), JSON.stringify(DEMO_PERIODS, null, 2))
writeFileSync(join(outputDir, 'demo_report.json'), JSON.stringify(DEMO_REPORT, null, 2))
writeFileSync(join(outputDir, 'demo_documents.json'), JSON.stringify(DEMO_DOCUMENTS, null, 2))
writeFileSync(join(outputDir, 'demo_profile.json'), JSON.stringify(DEMO_PROFILE, null, 2))

console.log('Successfully dumped demo data to:', outputDir)
